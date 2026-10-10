#!/usr/bin/env python3
"""Produktions-CLI fuer zeitlich begrenzte, schreibgeschuetzte VS1/P300-Fenster.

Die normale VS1-Regelung bleibt der Standard. Keine Anwendung dieses Werkzeugs
startet beim Boot, und keine Aktion schreibt Controller-Parameter.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import stat
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
LIB = HERE if (HERE / "handover_acceleration").is_dir() else Path("/usr/local/lib/optolink-hybrid")
sys.path.insert(0, str(LIB))

from handover_acceleration import continuous_canary, continuous_runtime, release_rollout, shadow_canary, stage_release
from handover_acceleration.producer_fence import LEASE_PATH

ROOT = release_rollout.ROOT
RELEASES = release_rollout.RELEASES
STAGES = ROOT / "staging"
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


class OperatorRejected(RuntimeError):
    pass


def _require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorRejected("Dieser Befehl erfordert root (sudo).")


def _validate_release_name(identifier: str) -> Path:
    if not IDENTIFIER.fullmatch(identifier) or identifier.startswith("-"):
        raise OperatorRejected("Ungueltige Release-Kennung.")
    path = RELEASES / identifier
    if path.is_symlink() or not path.is_dir():
        raise OperatorRejected("Nicht vorhandenes oder unsicheres Release.")
    return path


def _ensure_no_concurrent_canary() -> None:
    state = shadow_canary.status(continuous_canary.UNIT)
    if state not in ("inactive", "not-found", "failed"):
        raise OperatorRejected("Eine aktive Hybrid-Sitzung verhindert diese Aktion.")
    if (ROOT / "enrollment.json").exists():
        raise OperatorRejected("Hybrid-Enrollment vorhanden: zuerst Zustand pruefen.")
    if LEASE_PATH.exists():
        if LEASE_PATH.is_symlink() or not LEASE_PATH.is_file():
            raise OperatorRejected("Unbekannter persistenter Sperrmarker.")
        if LEASE_PATH.read_bytes():
            raise OperatorRejected("Schreiber-/P300-Sperre nicht leer; keine Freigabe.")


def status() -> dict:
    names = (*shadow_canary.ALL, "optolink-pump-override.service",
             continuous_canary.UNIT)
    unit_states = {}
    for name in names:
        try:
            unit_states[name] = shadow_canary.status(name)
        except (OSError, RuntimeError) as exc:
            unit_states[name] = "FEHLER_" + type(exc).__name__
    marker = "FEHLT"
    try:
        if LEASE_PATH.is_symlink():
            marker = "UNSICHER_SYMLINK"
        elif LEASE_PATH.exists():
            marker = ("FREI" if LEASE_PATH.read_bytes() == b""
                      else "NICHT_FREI")
    except OSError:
        marker = "NICHT_LESBAR"
    enrollment = ROOT / "enrollment.json"
    candidate_count = (sum(1 for p in RELEASES.iterdir()
                           if p.is_dir() and not p.is_symlink())
                       if RELEASES.is_dir() else 0)
    healthy = (all(unit_states.get(x) == "active" for x in shadow_canary.ALL)
               and unit_states.get(continuous_canary.UNIT) in ("inactive", "not-found")
               and marker == "FREI" and not enrollment.exists())
    return {
        "ergebnis": "VS1_BETRIEB_OK" if healthy else "PRUEFUNG_ERFORDERLICH",
        "serielle_schnittstelle": "Nur der bestehende optolink-splitter",
        "automatik_aktiv": unit_states.get(continuous_canary.UNIT) == "active",
        "dienste": unit_states,
        "sperre": marker,
        "enrollment_vorhanden": enrollment.exists(),
        "vorbereitete_releases": candidate_count,
        "keine_controller_writes": True,
    }


def prepare(identifier: str | None = None) -> dict:
    """Erzeugt eine exakt gehashte Kopie; kein systemd-/Optolink-Eingriff."""
    _require_root()
    _ensure_no_concurrent_canary()
    identifier = (identifier or
                  dt.datetime.now(dt.timezone.utc).strftime("hybrid-%Y%m%d-%H%M%S"))
    if not IDENTIFIER.fullmatch(identifier) or identifier.startswith("-"):
        raise OperatorRejected("Ungueltige Release-Kennung.")
    if (RELEASES / identifier).exists() or (RELEASES / identifier).is_symlink():
        raise OperatorRejected("Release bereits vorhanden; nie ueberschreiben.")
    STAGES.mkdir(parents=True, exist_ok=True, mode=0o700)
    if STAGES.is_symlink() or STAGES.stat().st_uid != 0 or STAGES.stat().st_mode & 0o077:
        raise OperatorRejected("Unsicheres Staging-Verzeichnis.")
    staging = STAGES / identifier
    if staging.exists() or staging.is_symlink():
        raise OperatorRejected("Staging-ID bereits belegt.")
    stage_release.stage(target=staging)
    try:
        release_rollout.stage_root_copy(staging, identifier)
    finally:
        # Only a precisely validated, owned ephemeral stage is removable.
        if (staging.parent == STAGES and not staging.is_symlink()
                and staging.is_dir() and staging.stat().st_uid == 0):
            shutil.rmtree(staging)
    return {
        "ergebnis": "VORBEREITET_NICHT_AKTIVIERT",
        "release": identifier,
        "pfad": str(RELEASES / identifier),
        "zeitlimit_standard_s": continuous_canary.MAX_RUNTIME_SECONDS,
        "serielle_aktionen": 0,
    }


def preflight(identifier: str) -> dict:
    _require_root()
    path = _validate_release_name(identifier)
    _ensure_no_concurrent_canary()
    # The immutable release includes an enrollment-draft.json file;
    # validate_staging() applies only before the root-side copy.
    report = shadow_canary.preflight(path)
    manifest = json.loads((path / "stage-manifest.json").read_text())
    return {
        "ergebnis": "PRUEFUNG_OK_KEINE_AKTIVIERUNG",
        "release": identifier,
        "dateien": len(manifest["generated_files"]),
        "gfa": report["gfa_before"],
        "dienste": report["before"],
    }


def canary(identifier: str, *, acknowledged: bool) -> dict:
    _require_root()
    if not acknowledged:
        raise OperatorRejected(
            "Explizite Option --telemetriepause-bestaetigt ist erforderlich.")
    path = _validate_release_name(identifier)
    _ensure_no_concurrent_canary()
    # Fixed three-window profile; longer stress tests and writes deliberately
    # are not exposed by this production-facing CLI.
    rc = continuous_canary.launch(path, profile="standard")
    return {
        "ergebnis": "BESTANDEN" if rc == 0 else "NICHT_VERIFIZIERT",
        "release": identifier,
        "rueckfall_durch": "systemd ExecStopPost",
        "returncode": rc,
    }


def _local_demand_rpc(payload: dict) -> dict:
    """Authenticated root -> exact original serial-owner PID Unix control."""
    _require_root()
    path = continuous_runtime.DEMAND_SOCKET_PATH
    try:
        node = path.lstat()
        parent = path.parent.lstat()
        if (not stat.S_ISSOCK(node.st_mode) or
                node.st_uid != pwd.getpwnam("optolink").pw_uid or
                node.st_mode & 0o077 or
                not stat.S_ISDIR(parent.st_mode) or
                parent.st_uid != node.st_uid or parent.st_mode & 0o077 or
                path.parent.resolve() != path.parent):
            raise OperatorRejected("Unvertrauenswuerdiger P300-Unix-Socket.")
        process = subprocess.check_output(
            ["systemctl", "show", "optolink-splitter.service",
             "--property=MainPID", "--value", "--no-pager"],
            timeout=4, text=True).strip()
        owner_pid = int(process)
        if owner_pid <= 1:
            raise OperatorRejected("Originaler Optolink-Hauptprozess nicht aktiv.")
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as conn:
            conn.settimeout(3.0)
            conn.connect(str(path))
            peer = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                   struct.calcsize("3i"))
            pid, uid, gid = struct.unpack("3i", peer)
            identity = pwd.getpwnam("optolink")
            if (pid != owner_pid or uid != identity.pw_uid or
                    gid != identity.pw_gid):
                raise OperatorRejected("Socket ist nicht der attestierte Hauptprozess.")
            wire = json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            if len(wire) > continuous_runtime.LocalDemandControl.MAX_PACKET:
                raise OperatorRejected("Ungueltige uebergrosse P300-Anfrage.")
            conn.sendall(wire)
            raw = conn.recv(2048)
            if not raw or len(raw) >= 2048:
                raise OperatorRejected("Keine gueltige P300-Antwort.")
            result = json.loads(raw.decode("utf-8"))
    except (FileNotFoundError, ConnectionError, TimeoutError,
            subprocess.SubprocessError, OSError, ValueError,
            UnicodeError) as exc:
        raise OperatorRejected(
            "On-Demand-Socket nicht aktiv oder nicht verifizierbar."
        ) from exc
    if (not isinstance(result, dict) or result.get("v") != 1 or
            type(result.get("ok")) is not bool):
        raise OperatorRejected("Ungueltige Kontrollantwort des Hauptprozesses.")
    return result


def demand_request(kind: str, ttl: int, *, acknowledged: bool,
                   request_id: str | None = None) -> dict:
    _require_root()
    if not acknowledged:
        raise OperatorRejected(
            "Explizites --lesefenster-bestaetigt fuer P300 erforderlich.")
    if type(kind) is not str or kind not in continuous_runtime._DEMAND_KINDS:
        raise OperatorRejected("Nur freigegebene P300-Read-only-Diagnosen.")
    if type(ttl) is not int or not 5 <= ttl <= 120:
        raise OperatorRejected("TTL muss zwischen 5 und 120 Sekunden liegen.")
    request_id = request_id or secrets.token_hex(16)
    if not continuous_runtime._DEMAND_ID.fullmatch(request_id):
        raise OperatorRejected("Ungueltige Auftrags-ID (32 Kleinbuchstaben-Hex).")
    return _local_demand_rpc({
        "v": 1, "op": "submit", "request_id": request_id,
        "kind": kind, "ttl_s": ttl})


def demand_lookup(request_id: str, session: str, *, cancel: bool = False) -> dict:
    _require_root()
    if (type(request_id) is not str or
            not continuous_runtime._DEMAND_ID.fullmatch(request_id) or
            type(session) is not str or
            not continuous_runtime._DEMAND_ID.fullmatch(session)):
        raise OperatorRejected("Sitzung und Auftrag muessen 32-stellige Hex-IDs sein.")
    return _local_demand_rpc({
        "v": 1, "op": "cancel" if cancel else "status",
        "request_id": request_id, "session": session})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    actions = p.add_subparsers(dest="aktion", required=True)
    actions.add_parser("status", help="Anlagen- und Schutzstatus, keine Hardware-Writes")
    cmd = actions.add_parser("vorbereiten", help="Root-eigenes, unveraenderliches Release anlegen")
    cmd.add_argument("--kennung", default=None)
    check = actions.add_parser("pruefen", help="Release- und VS1-Read-only-Vorpruefung")
    check.add_argument("kennung")
    test = actions.add_parser("testen", help="Drei beaufsichtigte, schreibgeschuetzte P300-Fenster")
    test.add_argument("kennung")
    test.add_argument("--telemetriepause-bestaetigt", action="store_true")
    demand = actions.add_parser(
        "anfordern", help="Root-only lokale P300-Diagnose im expliziten Shadow-Fenster")
    demand.add_argument("art", choices=sorted(continuous_runtime._DEMAND_KINDS))
    demand.add_argument("--ttl", type=int, default=90)
    demand.add_argument("--auftrag", default=None,
                        help="Wiederverwendbare 32-hex Idempotenzkennung")
    demand.add_argument("--lesefenster-bestaetigt", action="store_true")
    for command, explanation in (
        ("ergebnis", "Auftragsergebnis ohne Controller-I/O abfragen"),
        ("abbrechen", "Nur noch wartende Auftraege abbrechen")):
        q = actions.add_parser(command, help=explanation)
        q.add_argument("auftrag")
        q.add_argument("--sitzung", required=True)
    args = p.parse_args(argv)
    try:
        if args.aktion == "status":
            result = status()
        elif args.aktion == "vorbereiten":
            result = prepare(args.kennung)
        elif args.aktion == "pruefen":
            result = preflight(args.kennung)
        elif args.aktion == "testen":
            result = canary(args.kennung, acknowledged=args.telemetriepause_bestaetigt)
        elif args.aktion == "anfordern":
            result = demand_request(
                args.art, args.ttl, acknowledged=args.lesefenster_bestaetigt,
                request_id=args.auftrag)
        else:
            result = demand_lookup(
                args.auftrag, args.sitzung, cancel=args.aktion == "abbrechen")
    except (OperatorRejected, stage_release.StageRejected,
            release_rollout.RolloutRejected, shadow_canary.CanaryRejected,
            continuous_canary.ContinuousCanaryRejected) as exc:
        result = {"ergebnis": "VERWEIGERT", "grund": str(exc)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if "ok" in result:
        return 0 if result["ok"] is True else 1
    return 0 if result["ergebnis"] in (
        "VS1_BETRIEB_OK", "VORBEREITET_NICHT_AKTIVIERT",
        "PRUEFUNG_OK_KEINE_AKTIVIERUNG", "BESTANDEN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
