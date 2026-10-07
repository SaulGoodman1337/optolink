#!/usr/bin/env python3
"""Build an isolated P300 candidate; never modify /opt/optolink or start services.

Input must be the pristine pinned upstream. All existing production profile,
GFA dispatch, scheduler, discovery and /set readback patches are retained.
Default settings cannot open a device or connect to MQTT. See docs/p300-migration.md.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE_REF = "7bc69c32788dd19c7a35e787d0b2aa26c9548ce6"
UPSTREAM_REF = "c1ee204a1421447721603c5f21c6da7337fdac97"
PROFILE = ROOT / "config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py"

ADAPTER = '''
# optolink-p300-migration: opt-in backend; all serial I/O remains in the splitter.
if VS2:
    import optolink_p300
    import settings_ini as _p300_settings
    _p300_client = None

    def _p300(ser):
        global _p300_client
        if not getattr(_p300_settings, "p300_experimental", False):
            raise RuntimeError("P300 candidate requires explicit experimental acknowledgement")
        if settings.port_vitoconnect is not None:
            raise RuntimeError("This candidate does not support a second serial master")
        if _p300_client is None or _p300_client.serial is not ser:
            import logging
            _p300_client = optolink_p300.P300(
                ser,
                gap=settings.olbreath,
                ram_read=getattr(_p300_settings, "p300_ram_read", False),
                virtual_write=getattr(_p300_settings, "p300_virtual_write", False),
                audit=logging.getLogger("optolink.p300").warning,
            )
        return _p300_client

    def init_protocol(ser):
        return _p300(ser).initialize()

    def _p300_request(ser, function, addr, length, data=b"", protid=0):
        import utils
        result = _p300(ser).request(function, addr, length, data, protid)
        utils.comm_error(result[0] not in (1, 3, 0xAF))
        return result

    def read_datapoint_ext(addr, rdlen, ser):
        return _p300_request(ser, 1, addr, rdlen)

    def write_datapoint_ext(addr, data, ser):
        return _p300_request(ser, 2, addr, len(data), data)

    def read_gfa_ext(addr, rdlen, ser):
        return _p300_request(ser, 0xC9, addr, rdlen)

    def do_request(ser, fctcode, addr, rlen, data=b"", protid=0):
        return _p300_request(ser, fctcode, addr, rlen, data, protid)
'''

REQUEST_GUARD = '''    # optolink-p300-migration: do not bypass validation with opaque wire bytes.
    # writeraw/wraw are ordinary Virtual_WRITE and remain supported when enabled.
    if vs12_adapter.VS2 and isinstance(request, str):
        command = request.split(";", 1)[0].strip().lower()
        if ";" not in request or command == "raw":
            return 0xAF, bytearray(), None, "175;0x0;opaque-wire-command-disabled"
        if command == "ramread":
            fields = request.split(";")
            if len(fields) != 3:
                return 0xAF, bytearray(), None, "175;0x0;invalid-ramread"
            try:
                addr, length = int(fields[1], 0), int(fields[2], 0)
            except ValueError:
                return 0xAF, bytearray(), None, "175;0x0;invalid-ramread"
            code, addr, data = vs12_adapter.do_request(serViDev, 3, addr, length)
            value = utils.arr2hexstr(data) if data else "?"
            return code, data, value, get_retstr(code, addr, value)
'''


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def profile_inventory() -> dict:
    tree = ast.parse(PROFILE.read_text())
    profile = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "poll_list" for t in n.targets))
    items, counts = [], {}
    for domain in profile["domains"]:
        for block in [domain] + domain.get("units", []):
            items.extend(block.get("poll", []))
            counts[domain["domain"]] = counts.get(domain["domain"], 0) + sum(
                len(block.get(k, [])) for k in ("poll", "nopoll"))
    return {
        "base_ref": BASE_REF, "upstream_ref": UPSTREAM_REF,
        "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        "declared_entities": sum(counts.values()), "domains": counts,
        "poll_entries": len(items), "max_poll_length": max(i[3] for i in items),
        "gfa_entries": [i for i in items if str(i[4]).startswith("gfa:")],
        "live_verified": False, "release_gate": "BLOCKED_PENDING_20C2_P300_PARITY",
    }


def stage(upstream: Path, output: Path, settings_from: Path | None = None) -> dict:
    upstream, output = upstream.resolve(), output.resolve()
    if output.exists() or output.is_symlink():
        raise ValueError("output must not exist; no in-place deployment is supported")
    if output == Path("/opt/optolink") or output.is_relative_to(upstream):
        raise ValueError("refusing production path or output inside source")
    output.parent.mkdir(parents=True, exist_ok=True)
    patchers = [load(HERE / name) for name in (
        "optolink-apply-vs1-gfa-readonly-patch.py",
        "optolink-apply-phased-poll-scheduler-patch.py")]
    for module in patchers:
        for name, sha in module.BASE_BLOBS.items():
            if blob((upstream / name).read_bytes()) != sha:
                raise ValueError(f"not pristine pinned upstream: {name}")
    # Ensure unpatched transport corresponds to the audited upstream too.
    if blob((upstream / "optolinkvs2.py").read_bytes()) != "7d56f71b10d1bbb74ba2efb443bd16161aff71a8":
        raise ValueError("unexpected upstream P300 source")
    inventory = profile_inventory()
    if inventory["max_poll_length"] > 55:
        raise ValueError("profile contains unsupported long virtual objects; do not blindly chunk")
    with tempfile.TemporaryDirectory(prefix=".p300-stage-", dir=output.parent) as tmp:
        dest = Path(tmp) / "runtime"
        shutil.copytree(upstream, dest, ignore=shutil.ignore_patterns(".git", "venv", "__pycache__", "*.log", "settings_ini.py"))
        dest.chmod(0o700)
        for module in patchers:
            for name, patch in module.PATCHERS.items():
                path = dest / name
                path.write_text(patch(path.read_bytes().decode()))
        shutil.copy2(PROFILE, dest / "homeassistant_poll_list.py")
        (dest / "poll_list.py").unlink(missing_ok=True)
        shutil.copy2(HERE / "optolink_p300.py", dest / "optolink_p300.py")
        # Reuse the EXACT production discovery and MQTT-readback patches.
        helper = (HERE / "optolink-apply-vdensho1-ha-profile.sh").read_text()
        for variable, target in (("publisher", "homeassistant_publish.py"), ("mqtt_module", "mqtt_util.py")):
            marker = 'python3 - "$' + variable + '" <<\'PY\'\n'
            if helper.count(marker) != 1:
                raise ValueError(f"ambiguous production patch: {variable}")
            program = helper.split(marker, 1)[1].split("\nPY\n", 1)[0]
            subprocess.run([sys.executable, "-", str(dest / target)], input=program, text=True, check=True)
        path = dest / "vs12_adapter.py"
        path.write_text(path.read_text() + ADAPTER)
        path = dest / "requests_util.py"
        text = path.read_text()
        marker = "    # error handling in calling proc\n"
        if text.count(marker) != 1:
            raise ValueError("request dispatcher marker mismatch")
        path.write_text(text.replace(marker, REQUEST_GUARD + marker, 1))
        settings = settings_from.read_text() if settings_from else (
            "port_optolink = None\nport_vitoconnect = None\nmqtt_broker = None\n"
            "mqtt_listen = None\ntcpip_port = None\nno_logger_file = True\nshow_opto_rx = False\n")
        # An existing settings module may contain credentials; never print it.
        parsed = ast.parse(settings)
        values = {}
        for n in parsed.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                try:
                    values[n.targets[0].id] = ast.literal_eval(n.value)
                except (ValueError, TypeError):
                    pass
        if settings_from and ("port_vitoconnect" not in values or values["port_vitoconnect"] is not None):
            raise ValueError("settings must explicitly disable a second serial master")
        settings += ("\n# EXPERIMENTAL P300: no live parity claim; writes disabled.\n"
                     "vs1protocol = False\nolbreath = 0.025\np300_experimental = True\n"
                     "p300_virtual_write = False\np300_ram_read = False\n")
        path = dest / "settings_ini.py"
        path.write_text(settings)
        path.chmod(0o600)
        for path in dest.glob("*.py"):
            py_compile.compile(str(path), doraise=True)
        (dest / "p300-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
        dest.rename(output)
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings-from", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.upstream, args.output, args.settings_from), indent=2))
    print("STAGED_ONLY: no service, serial port, MQTT connection or production file was touched")


if __name__ == "__main__":
    main()
