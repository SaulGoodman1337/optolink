#!/usr/bin/env python3
"""Guarded stock optolink-splitter permanent-VS1 smoke test for WB2A/20C2.

This helper does NOT patch splitter source code and does NOT send direct Optolink
writes itself. It temporarily changes only local splitter runtime settings:

    vs1protocol = True
    mqtt_listen = None
    tcpip_port = None
    olbreath = 0.15

The original /opt/optolink/settings_ini.py bytes, mode and ownership are saved
and restored exactly before the normal services are restarted.

During the temporary 30-second run it validates:
- the stock splitter process stays active with a stable MainPID;
- journal shows VS1/KW initialization and no known poll/protocol restart errors;
- MQTT read publications from the installed Home Assistant poll list arrive;
- every poll item enabled on cycle 0 is seen at least once (retained messages
  received before the test window are excluded).

The party emulator is stopped during the smoke test. Incoming MQTT command/set
handling is disabled by mqtt_listen=None, and TCP ingress by tcpip_port=None.
No production GFA polling is added by this test.

Default is plan only. --self-test performs offline tests. --execute performs the
live 30-second gate. Software cleanup cannot guarantee restoration after
SIGKILL, host power loss, storage failure, or other catastrophic interruption.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

VERSION = "1.0.1"
ROOT = Path("/opt/optolink")
SETTINGS = ROOT / "settings_ini.py"
HA_POLL = ROOT / "homeassistant_poll_list.py"
LEGACY_POLL = ROOT / "poll_list.py"
SPLITTER = "optolink-splitter.service"
PARTY = "optolink-party-emulator.service"
DEFAULT_SECONDS = 30
MIN_SECONDS = 20
MAX_SECONDS = 60
TEMP_SETTINGS = {
    "vs1protocol": True,
    "mqtt_listen": None,
    "tcpip_port": None,
    "olbreath": 0.15,
}
UPSTREAM_REF = "c1ee204a1421447721603c5f21c6da7337fdac97"
UPSTREAM_RUNTIME_BLOBS = {
    "optolinkvs2_switch.py": "1fae36baae1c2ef264906c8eca76ef15c5152974",
    "optolinkvs1.py": "cff6b4d8d52ca4ee1f79c310dd9377dba1a18270",
    "optolinkvs2.py": "7d56f71b10d1bbb74ba2efb443bd16161aff71a8",
    "vs12_adapter.py": "dfcd97cbe598bb71aafd5c1735e1fb4018b8be68",
    "requests_util.py": "0e2b94547518bde504632579d5d7c4da45e56db7",
    "c_polllist.py": "2502f9b7bf2b4bd2b218286e135b9694191f970b",
    "c_settings_adapter.py": "a2d300d056a49b4bdfdbed81a93860405e478e29",
    "mqtt_util.py": "c10850f560564936064178dda605ad821c5af13d",
    "homeassistant_adapter.py": "d6b1e7b4e8446e23ea4f26c90cafc26c43e031c4",
    "homeassistant_publish.py": "0e34f9f11d1be07de1e58b5baa71cfe62efb2851",
    "utils.py": "ee10204b61bb1fd5a75d20c8b0901262096baf2e",
    "c_tcpserver.py": "572eef3637ce39825bb73aa024b4a9050429e147",
    "viessdata_util.py": "2d6f93be508ef944befe30e64ce7b7313f903203",
    "viconn_util.py": "bf6f916b20ed66746b869d4ec660542304ec6d00",
}
ERROR_PATTERNS = (
    "Traceback (most recent call last)",
    "Timeout waiting for 0x05",
    "OL Error do_poll_item",
    "Error do_poll_item",
    "too many restarts",
    "init_protocol VS1/KW failed",
    "Error handling MQTT request",
    "main\n",
)


class SmokeError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(cmd: list[str], *, check: bool = True, timeout: float | None = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          check=check, timeout=timeout)


def systemctl_show(unit: str) -> dict[str, str]:
    cp = run(["systemctl", "show", unit,
              "-p", "LoadState", "-p", "ActiveState", "-p", "SubState",
              "-p", "MainPID", "-p", "NRestarts"], timeout=10)
    result: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def unit_running(state: dict[str, str]) -> bool:
    return state.get("LoadState") == "loaded" and state.get("ActiveState") == "active" and state.get("SubState") == "running"


def parse_top_level_assignments(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    result: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            try:
                result[targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                pass
    return result


def patch_assignments_exact(source: str, replacements: dict[str, Any]) -> str:
    tree = ast.parse(source)
    nodes: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) == 1 and isinstance(targets[0], ast.Name) and targets[0].id in replacements:
                name = targets[0].id
                if name in nodes:
                    raise SmokeError(f"Multiple top-level assignments for {name}.")
                nodes[name] = node
    missing = sorted(set(replacements) - set(nodes))
    if missing:
        raise SmokeError("Missing settings assignments: " + ", ".join(missing))

    lines = source.splitlines(keepends=True)
    for name, node in nodes.items():
        lineno = getattr(node, "lineno", 0)
        end_lineno = getattr(node, "end_lineno", lineno)
        if lineno != end_lineno or lineno < 1:
            raise SmokeError(f"Setting {name} must be a one-line top-level assignment.")
        old = lines[lineno - 1]
        eol = "\r\n" if old.endswith("\r\n") else "\n" if old.endswith("\n") else ""
        lines[lineno - 1] = f"{name} = {repr(replacements[name])}{eol}"
    patched = "".join(lines)
    ast.parse(patched)
    parsed = parse_top_level_assignments(patched)
    for name, expected in replacements.items():
        if parsed.get(name) != expected:
            raise SmokeError(f"Temporary settings verification failed for {name}.")
    return patched


def atomic_write_like(path: Path, data: bytes, st: os.stat_result) -> None:
    fd, tmppath = tempfile.mkstemp(prefix=path.name + ".smoke.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmppath, stat.S_IMODE(st.st_mode))
        os.chown(tmppath, st.st_uid, st.st_gid)
        os.replace(tmppath, path)
        dirfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(tmppath):
            os.unlink(tmppath)


def literal_poll_list(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "poll_list":
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, dict):
                        raise SmokeError("poll_list is not a literal dictionary.")
                    return value
    raise SmokeError("No literal poll_list assignment found.")


def flatten_poll_items(poll_cfg: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for domain in poll_cfg.get("domains", []):
        items.extend(domain.get("poll", []) or [])
        for unit in domain.get("units", []) or []:
            items.extend(unit.get("poll", []) or [])
    return items


def expected_cycle0_topics(poll_cfg: dict[str, Any], mqtt_topic: str, mqtt_fstr: str) -> dict[str, str]:
    groups = poll_cfg.get("poll_groups", {}) or {}
    result: dict[str, str] = {}
    for item in flatten_poll_items(poll_cfg):
        if isinstance(item, (tuple, list)):
            if len(item) < 4:
                continue
            group, name, addr = item[0], item[1], item[2]
        elif isinstance(item, dict):
            group = item.get("poll_group", item.get("group", "FAST"))
            name = item.get("name")
            addr = item.get("dpaddr", item.get("address", item.get("dpaddr_str")))
        else:
            continue
        cycle = groups.get(group, group if isinstance(group, int) else 1)
        try:
            cycle_i = int(cycle)
        except Exception:
            raise SmokeError(f"Unknown poll group {group!r} for {name!r}.")
        if cycle_i < 0:
            continue
        if not name or addr is None:
            continue
        if isinstance(addr, str):
            addr_i = int(addr, 0)
        else:
            addr_i = int(addr)
        suffix = mqtt_fstr.format(dpaddr=addr_i, dpname=name)
        topic = mqtt_topic.rstrip("/") + "/" + suffix
        if topic in result and result[topic] != name:
            raise SmokeError(f"MQTT topic collision: {topic} for {result[topic]} and {name}.")
        result[topic] = str(name)
    if not result:
        raise SmokeError("No enabled poll topics found for cycle 0.")
    return result


def import_module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SmokeError(f"Cannot load {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MqttCapture:
    def __init__(self, settings: dict[str, Any], expected: dict[str, str], log):
        self.settings = settings
        self.expected = expected
        self.log = log
        self.lock = threading.Lock()
        self.seen: dict[str, tuple[str, float]] = {}
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.client = None

    def start(self):
        try:
            import paho.mqtt.client as paho
        except Exception as exc:
            raise SmokeError("paho-mqtt unavailable in executing Python environment.") from exc

        broker = self.settings.get("mqtt_broker")
        if not broker:
            raise SmokeError("mqtt_broker is disabled; HA MQTT smoke validation cannot run.")
        host, port_text = str(broker).rsplit(":", 1)
        port = int(port_text)
        client_id = f"wb2a_vs1_smoke_{os.getpid()}"
        try:
            client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id)
        except Exception:
            client = paho.Client(client_id=client_id)

        creds = self.settings.get("mqtt_user")
        if creds is not None and str(creds).strip():
            text = str(creds).strip()
            if ":" in text:
                user, password = text.split(":", 1)
                client.username_pw_set(user, password=password or None)
            else:
                client.username_pw_set(text, password=None)

        if bool(self.settings.get("mqtt_tls_enable", False)):
            import ssl
            skip = bool(self.settings.get("mqtt_tls_skip_verify", False))
            client.tls_set(
                ca_certs=self.settings.get("mqtt_tls_ca_certs"),
                certfile=self.settings.get("mqtt_tls_certfile"),
                keyfile=self.settings.get("mqtt_tls_keyfile"),
                cert_reqs=ssl.CERT_NONE if skip else ssl.CERT_REQUIRED,
                tls_version=getattr(ssl, "PROTOCOL_TLS_CLIENT", ssl.PROTOCOL_TLS),
            )
            client.tls_insecure_set(skip)

        def on_connect(c, userdata, flags, reason_code, properties=None):
            if int(reason_code) != 0:
                self.log(f"MQTT_SUB_CONNECT_ERROR={reason_code}")
                return
            self.connected.set()
            c.subscribe(str(self.settings["mqtt_topic"]).rstrip("/") + "/#", qos=0)

        def on_subscribe(c, userdata, mid, reason_codes=None, properties=None):
            self.subscribed.set()

        def on_message(c, userdata, msg):
            if msg.retain:
                return
            topic = str(msg.topic)
            if topic not in self.expected:
                return
            try:
                payload = msg.payload.decode("utf-8", errors="replace")
            except Exception:
                payload = repr(msg.payload)
            with self.lock:
                self.seen[topic] = (payload, time.monotonic())

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.connect(host, port, keepalive=30)
        client.loop_start()
        self.client = client
        if not self.connected.wait(5):
            self.stop()
            raise SmokeError("MQTT validation subscriber did not connect within 5 seconds.")
        if not self.subscribed.wait(5):
            self.stop()
            raise SmokeError("MQTT validation subscriber did not subscribe within 5 seconds.")
        time.sleep(0.25)
        self.clear()
        self.log(f"MQTT_SUBSCRIBED_BASE={str(self.settings['mqtt_topic']).rstrip('/')}/#")

    def clear(self):
        with self.lock:
            self.seen.clear()

    def count(self) -> int:
        with self.lock:
            return len(self.seen)

    def missing(self) -> list[str]:
        with self.lock:
            return [topic for topic in self.expected if topic not in self.seen]

    def snapshot(self) -> dict[str, tuple[str, float]]:
        with self.lock:
            return dict(self.seen)

    def stop(self):
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
            try:
                self.client.loop_stop()
            except Exception:
                pass
            self.client = None


class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.handle = path.open("a", encoding="utf-8", buffering=1)
    def __call__(self, msg: str):
        line = f"{dt.datetime.now().astimezone().isoformat(timespec='milliseconds')} {msg}"
        print(line, flush=True)
        self.handle.write(line + "\n")
    def close(self):
        self.handle.close()


def journal_since(epoch_seconds: float) -> str:
    cp = run(["journalctl", "-u", SPLITTER, "--since", f"@{epoch_seconds:.3f}",
              "--no-pager", "-o", "short-iso-precise"], check=False, timeout=15)
    return cp.stdout


def analyze_journal(text: str) -> tuple[list[str], dict[str, bool]]:
    hits = [p for p in ERROR_PATTERNS if p in text]
    flags = {
        "vs1_initialized": "VS1/KW protocol initialized" in text,
        "main_loop": "enter main loop" in text,
        "unexpected_restart": "re-start #" in text,
    }
    return hits, flags


def load_effective_settings() -> dict[str, Any]:
    old_cwd = os.getcwd()
    sys_path_added = False
    try:
        os.chdir(ROOT)
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
            sys_path_added = True
        from c_settings_adapter import settings  # type: ignore
        keys = [
            "port_vitoconnect", "mqtt_broker", "mqtt_user", "mqtt_topic", "mqtt_fstr",
            "mqtt_tls_enable", "mqtt_tls_skip_verify", "mqtt_tls_ca_certs",
            "mqtt_tls_certfile", "mqtt_tls_keyfile", "mqtt_no_redundant",
            "mqtt_listen", "tcpip_port", "vs1protocol", "olbreath",
        ]
        return {k: getattr(settings, k, None) for k in keys}
    finally:
        os.chdir(old_cwd)
        if sys_path_added:
            try:
                sys.path.remove(str(ROOT))
            except ValueError:
                pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_stock_runtime() -> tuple[str, str]:
    """Verify installed runtime without requiring .git metadata.

    Preferred mode is a clean Git checkout at origin/main. Migrated/legacy
    installations without .git are accepted only when every critical runtime
    Python file matches the pinned upstream Git blob manifest exactly.
    """
    git_dir = ROOT / ".git"
    if git_dir.exists():
        try:
            head = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], timeout=10).stdout.strip()
            origin = run(["git", "-C", str(ROOT), "rev-parse", "origin/main"], timeout=10).stdout.strip()
            dirty = run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], timeout=10).stdout.strip()
        except Exception as exc:
            raise SmokeError("Git metadata exists but stock verification failed: " + str(exc)) from exc
        if head != origin:
            raise SmokeError(f"Tracked splitter checkout HEAD {head} != origin/main {origin}.")
        if dirty:
            raise SmokeError("Tracked splitter checkout has local modifications: " + dirty.replace("\n", " | "))
        return "git-clean-origin-main", head

    mismatches: list[str] = []
    for rel, expected in UPSTREAM_RUNTIME_BLOBS.items():
        path = ROOT / rel
        if not path.is_file():
            mismatches.append(f"{rel}:missing")
            continue
        actual = git_blob_sha(path)
        if actual != expected:
            mismatches.append(f"{rel}:{actual}!={expected}")
    if mismatches:
        raise SmokeError(
            "No .git metadata and runtime hash-manifest mismatch against upstream "
            + UPSTREAM_REF + ": " + " ; ".join(mismatches)
        )
    return "runtime-blob-manifest", UPSTREAM_REF


def duration_arg(text: str) -> int:
    try:
        value = int(text)
    except Exception as exc:
        raise argparse.ArgumentTypeError("seconds must be an integer") from exc
    if not MIN_SECONDS <= value <= MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"seconds must be {MIN_SECONDS}..{MAX_SECONDS}")
    return value


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_patch_exact(self):
            src = "vs1protocol = False\nmqtt_listen = 'x'\ntcpip_port = 1\nolbreath = 0.05\nother = 7\n"
            out = patch_assignments_exact(src, TEMP_SETTINGS)
            vals = parse_top_level_assignments(out)
            for key, value in TEMP_SETTINGS.items():
                self.assertEqual(vals[key], value)
            self.assertIn("other = 7", out)

        def test_patch_missing_refused(self):
            with self.assertRaises(SmokeError):
                patch_assignments_exact("vs1protocol=False\n", TEMP_SETTINGS)

        def test_literal_assignments(self):
            vals = parse_top_level_assignments("a=1\nb='x'\nc=None\n")
            self.assertEqual(vals, {"a": 1, "b": "x", "c": None})

        def test_poll_expected_cycle0(self):
            cfg = {
                "poll_groups": {"FAST": 1, "DISABLED": -1, "ONCE": 0},
                "domains": [{"poll": [
                    ("FAST", "a", 0x1000, 1, 1, False),
                    ("DISABLED", "b", 0x1001, 1, 1, False),
                    ("ONCE", "c", 0x1002, 1, 1, False),
                ]}],
            }
            got = expected_cycle0_topics(cfg, "openv", "{dpname}")
            self.assertEqual(got, {"openv/a": "a", "openv/c": "c"})

        def test_poll_topic_format_addr(self):
            cfg = {"poll_groups": {"FAST": 1}, "domains": [{"poll": [("FAST", "x", 0x1234, 1)]}]}
            got = expected_cycle0_topics(cfg, "vito", "{dpaddr:04X}_{dpname}")
            self.assertEqual(got, {"vito/1234_x": "x"})

        def test_topic_collision_refused(self):
            cfg = {"poll_groups": {"FAST": 1}, "domains": [{"poll": [
                ("FAST", "x", 0x1000, 1), ("FAST", "y", 0x1001, 1),
            ]}]}
            with self.assertRaises(SmokeError):
                expected_cycle0_topics(cfg, "vito", "fixed")

        def test_journal_good(self):
            hits, flags = analyze_journal("VS1/KW protocol initialized\nenter main loop\n")
            self.assertEqual(hits, [])
            self.assertTrue(flags["vs1_initialized"])
            self.assertTrue(flags["main_loop"])
            self.assertFalse(flags["unexpected_restart"])

        def test_journal_bad(self):
            hits, flags = analyze_journal("VS1/KW protocol initialized\nOL Error do_poll_item 3\nre-start #1\n")
            self.assertIn("OL Error do_poll_item", hits)
            self.assertTrue(flags["unexpected_restart"])

        def test_git_blob_sha(self):
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "x"
                p.write_bytes(b"test\n")
                self.assertEqual(git_blob_sha(p), "9daeafb9864cf43055ae93beb0afd6c7d144bfa4")

        def test_duration(self):
            self.assertEqual(duration_arg("30"), 30)
            for x in ("19", "61", "bad"):
                with self.assertRaises(argparse.ArgumentTypeError):
                    duration_arg(x)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if result.wasSuccessful():
        print("LOCAL_STOCK_VS1_SMOKE_TESTS=10/10")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--execute", action="store_true")
    group.add_argument("--self-test", action="store_true")
    parser.add_argument("--seconds", type=duration_arg, default=DEFAULT_SECONDS)
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A stock splitter VS1 smoke {VERSION}: plan only; no service/settings changes.\n"
            f"Live gate: {args.seconds}s stock splitter with vs1protocol=True, mqtt_listen=None, "
            "tcpip_port=None, olbreath=0.15; exact settings restore afterwards.\n"
            "Requires either a clean tracked /opt/optolink checkout or an exact pinned "
            "upstream runtime-file manifest, no legacy poll_list.py, homeassistant_poll_list.py "
            "present, port_vitoconnect=None. --execute required."
        )
        return 0
    if os.geteuid() != 0:
        print("ERROR: --execute requires root.", file=sys.stderr)
        return 1

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log = Logger(Path("/root") / f"wb2a-stock-vs1-smoke-{stamp}-{os.getpid()}.log")
    backup = Path("/root") / f"settings_ini.py.vs1-smoke-backup-{stamp}-{os.getpid()}"
    journal_path = Path("/root") / f"wb2a-stock-vs1-smoke-{stamp}-{os.getpid()}.journal.log"
    mqtt_path = Path("/root") / f"wb2a-stock-vs1-smoke-{stamp}-{os.getpid()}.mqtt.json"

    original_bytes: bytes | None = None
    settings_stat: os.stat_result | None = None
    original_sha = None
    temp_sha = None
    restored = False
    splitter_was_running = False
    party_was_running = False
    subscriber: MqttCapture | None = None
    test_started_epoch = 0.0
    live_result = False
    failures: list[str] = []
    previous_handlers: dict[int, Any] = {}

    def abort(signum, _frame):
        raise SmokeError(f"Interrupted by signal {signum}; entering cleanup.")

    previous_handlers = {
        sig: signal.signal(sig, abort)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    }

    try:
        log(f"WB2A stock splitter VS1 smoke {VERSION}; seconds={args.seconds}")
        log("SOURCE_PATCH=no; OPTO_WRITE_BY_HELPER=no; GFA_POLL_PATCH=no")
        log(f"SETTINGS={SETTINGS}; HA_POLL={HA_POLL}")

        if not SETTINGS.is_file():
            raise SmokeError(f"Missing {SETTINGS}.")
        if LEGACY_POLL.exists():
            raise SmokeError("Legacy /opt/optolink/poll_list.py exists and would take precedence; aborting.")
        if not HA_POLL.is_file():
            raise SmokeError("Missing /opt/optolink/homeassistant_poll_list.py.")

        stock_mode, stock_ref = verify_stock_runtime()
        log(f"STOCK_VERIFY_MODE={stock_mode}")
        log(f"STOCK_VERIFY_REF={stock_ref}")
        if stock_mode == "git-clean-origin-main":
            log("TRACKED_CHECKOUT=clean_origin_main")
        else:
            log(f"RUNTIME_BLOB_MANIFEST=match files={len(UPSTREAM_RUNTIME_BLOBS)}")

        effective = load_effective_settings()
        if effective.get("port_vitoconnect") is not None:
            raise SmokeError("port_vitoconnect must be None for this gate.")
        if bool(effective.get("vs1protocol")):
            raise SmokeError("Production vs1protocol is already True; expected baseline False.")
        if not effective.get("mqtt_broker") or not effective.get("mqtt_topic"):
            raise SmokeError("MQTT must be configured for the HA poll-output validation.")

        poll_cfg = literal_poll_list(HA_POLL)
        mqtt_fstr = str(effective.get("mqtt_fstr") or "{dpname}")
        expected = expected_cycle0_topics(poll_cfg, str(effective["mqtt_topic"]), mqtt_fstr)
        log(f"EXPECTED_CYCLE0_MQTT_TOPICS={len(expected)}")

        splitter_state = systemctl_show(SPLITTER)
        party_state = systemctl_show(PARTY)
        splitter_was_running = unit_running(splitter_state)
        party_was_running = unit_running(party_state)
        if not splitter_was_running:
            raise SmokeError("Require optolink-splitter.service running before test.")
        if party_state.get("ActiveState") in ("activating", "deactivating", "reloading"):
            raise SmokeError("Party emulator is transitioning; aborting.")

        original_bytes = SETTINGS.read_bytes()
        settings_stat = SETTINGS.stat()
        original_sha = sha256_bytes(original_bytes)
        backup.write_bytes(original_bytes)
        os.chmod(backup, 0o600)
        log(f"ORIGINAL_SETTINGS_SHA256={original_sha}")
        log(f"BACKUP_PATH={backup}")

        original_source = original_bytes.decode("utf-8")
        original_literals = parse_top_level_assignments(original_source)
        for required in TEMP_SETTINGS:
            if required not in original_literals:
                raise SmokeError(f"settings_ini.py lacks explicit top-level assignment {required}; refusing rewrite.")
        if original_literals.get("vs1protocol") is not False:
            raise SmokeError("Literal settings baseline vs1protocol is not False.")

        if party_was_running:
            log("Stopping " + PARTY)
            run(["systemctl", "stop", PARTY], timeout=15)
        log("Stopping " + SPLITTER)
        run(["systemctl", "stop", SPLITTER], timeout=15)

        subscriber = MqttCapture(effective, expected, log)
        subscriber.start()

        patched_source = patch_assignments_exact(original_source, TEMP_SETTINGS)
        patched_bytes = patched_source.encode("utf-8")
        atomic_write_like(SETTINGS, patched_bytes, settings_stat)
        temp_sha = sha256_bytes(SETTINGS.read_bytes())
        if temp_sha != sha256_bytes(patched_bytes):
            raise SmokeError("Temporary settings byte verification failed.")
        temp_literals = parse_top_level_assignments(SETTINGS.read_text(encoding="utf-8"))
        for key, value in TEMP_SETTINGS.items():
            if temp_literals.get(key) != value:
                raise SmokeError(f"Temporary settings readback failed for {key}.")
        log(f"TEMP_SETTINGS_SHA256={temp_sha}")
        log("TEMP_SETTINGS=vs1protocol:true,mqtt_listen:none,tcpip_port:none,olbreath:0.15")

        subscriber.clear()
        test_started_epoch = time.time()
        log("Starting stock " + SPLITTER + " with temporary VS1 settings")
        run(["systemctl", "start", SPLITTER], timeout=15)
        time.sleep(1.0)
        live_state = systemctl_show(SPLITTER)
        if not unit_running(live_state):
            raise SmokeError("Stock splitter did not reach active/running in VS1 mode.")
        main_pid = int(live_state.get("MainPID", "0") or "0")
        if main_pid <= 1:
            raise SmokeError("Invalid MainPID after VS1 start.")
        log(f"VS1_MAINPID={main_pid}")

        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
            state = systemctl_show(SPLITTER)
            if not unit_running(state):
                raise SmokeError("Stock splitter left active/running during smoke window.")
            if int(state.get("MainPID", "0") or "0") != main_pid:
                raise SmokeError("Stock splitter MainPID changed during smoke window.")

        test_journal = journal_since(test_started_epoch)
        journal_path.write_text(test_journal, encoding="utf-8")
        jhits, jflags = analyze_journal(test_journal)
        log(f"JOURNAL_VS1_INITIALIZED={'yes' if jflags['vs1_initialized'] else 'no'}")
        log(f"JOURNAL_MAIN_LOOP={'yes' if jflags['main_loop'] else 'no'}")
        log(f"JOURNAL_UNEXPECTED_RESTART={'yes' if jflags['unexpected_restart'] else 'no'}")
        if jhits:
            failures.append("Journal error patterns: " + ", ".join(jhits))
        if not jflags["vs1_initialized"]:
            failures.append("Journal did not confirm VS1/KW protocol initialized.")
        if not jflags["main_loop"]:
            failures.append("Journal did not confirm entry into main loop.")
        if jflags["unexpected_restart"]:
            failures.append("Splitter logged an unexpected internal restart.")

        seen = subscriber.snapshot()
        missing = subscriber.missing()
        mqtt_path.write_text(json.dumps({
            "expected_count": len(expected),
            "seen_count": len(seen),
            "missing": [{"topic": t, "name": expected[t]} for t in missing],
            "seen": [{"topic": t, "name": expected[t], "payload": seen[t][0]} for t in sorted(seen)],
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"MQTT_EXPECTED={len(expected)}")
        log(f"MQTT_SEEN={len(seen)}")
        log(f"MQTT_MISSING={len(missing)}")
        if missing:
            failures.append(f"Missing {len(missing)} enabled cycle-0 MQTT poll topics.")
            for topic in missing[:20]:
                log(f"MQTT_MISSING_TOPIC={topic} name={expected[topic]}")
            if len(missing) > 20:
                log(f"MQTT_MISSING_MORE={len(missing)-20}")

        live_result = not failures
    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log("SMOKE_FAILED: " + failures[-1])
    finally:
        for sig, handler in previous_handlers.items():
            try:
                signal.signal(sig, signal.SIG_IGN)
            except Exception:
                pass
        try:
            if subscriber is not None:
                subscriber.stop()

            current = systemctl_show(SPLITTER)
            if unit_running(current):
                log("Stopping temporary VS1 " + SPLITTER)
                try:
                    run(["systemctl", "stop", SPLITTER], timeout=15)
                except Exception as exc:
                    failures.append("Failed to stop temporary VS1 splitter: " + str(exc))

            if original_bytes is not None and settings_stat is not None:
                try:
                    atomic_write_like(SETTINGS, original_bytes, settings_stat)
                    restored_sha = sha256_bytes(SETTINGS.read_bytes())
                    restored = restored_sha == original_sha
                    log(f"RESTORED_SETTINGS_SHA256={restored_sha}")
                    log("SETTINGS_RESTORED=" + ("yes" if restored else "NO"))
                    if not restored:
                        failures.append("CRITICAL: settings_ini.py byte-exact restore verification failed.")
                except Exception as exc:
                    failures.append("CRITICAL: settings_ini.py restore failed: " + str(exc))
                    log(failures[-1])

            if splitter_was_running:
                try:
                    log("Restoring running state: " + SPLITTER)
                    run(["systemctl", "start", SPLITTER], timeout=15)
                    time.sleep(1.0)
                    if not unit_running(systemctl_show(SPLITTER)):
                        raise SmokeError("restored splitter is not active/running")
                    log("SERVICE_RESTORED=" + SPLITTER + " running")
                except Exception as exc:
                    failures.append("Restart failed: " + SPLITTER + ": " + str(exc))

            if party_was_running:
                try:
                    log("Restoring running state: " + PARTY)
                    run(["systemctl", "start", PARTY], timeout=15)
                    time.sleep(1.0)
                    if not unit_running(systemctl_show(PARTY)):
                        raise SmokeError("restored party emulator is not active/running")
                    log("SERVICE_RESTORED=" + PARTY + " running")
                except Exception as exc:
                    failures.append("Restart failed: " + PARTY + ": " + str(exc))

            if restored and backup.exists():
                try:
                    backup.unlink()
                    log("BACKUP_REMOVED=yes")
                except Exception as exc:
                    log("BACKUP_REMOVE_WARNING=" + str(exc))
            elif backup.exists():
                log(f"BACKUP_RETAINED={backup}")

            if splitter_was_running and restored:
                restored_journal = journal_since(time.time() - 5)
                restored_vs2 = "VS2/300 protocol initialized" in restored_journal
                log("RESTORED_BASELINE_PROTOCOL=" + ("VS2/300" if restored_vs2 else "NOT_CONFIRMED"))
                if not restored_vs2:
                    failures.append("Restored splitter did not log VS2/300 protocol initialized within verification window.")
        finally:
            for sig, handler in previous_handlers.items():
                try:
                    signal.signal(sig, handler)
                except Exception:
                    pass

    result_ok = live_result and restored and splitter_was_running and unit_running(systemctl_show(SPLITTER)) and not failures
    if party_was_running:
        result_ok = result_ok and unit_running(systemctl_show(PARTY))

    log(f"JOURNAL={journal_path}")
    log(f"MQTT_CAPTURE={mqtt_path}")
    log("RESULT=" + ("PASS" if result_ok else "FAIL"))
    log("PASS means stock splitter permanent-VS1 read polling + MQTT publication passed this bounded gate and original settings/services were restored.")
    log("PASS does not validate VS1 writes, GFA production polling, long-duration FF behavior, or catastrophic-interruption recovery.")
    for failure in failures:
        log("ERROR: " + failure)
    log("LOG=" + str(log.path))
    log.close()
    return 0 if result_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
