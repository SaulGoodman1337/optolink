"""End-to-end GWG owner-path tests against copies of REAL production runtime files.

CI can skip absent private runtime, but the installed LXC MUST run these.
Nothing imports the live daemon in this test process or opens the real serial port.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("/opt/optolink")
PATCH = ROOT / "tools" / "optolink-apply-gwg-readonly-patch.py"
TEST_SUBPROCESS = r'''
import json
import logging
import pathlib
import sys
import time
import types

stage, prod = sys.argv[1:]
logger_mod = types.ModuleType("logger_util")
logger_mod.logger = logging.getLogger("gwg-test-only")
sys.modules["logger_util"] = logger_mod
sys.path[:0] = [stage, prod]

import vs12_adapter
import requests_util

assert pathlib.Path(vs12_adapter.__file__).parent == pathlib.Path(stage)
assert pathlib.Path(requests_util.__file__).parent == pathlib.Path(stage)
assert pathlib.Path(vs12_adapter.optolinkgwg.__file__).parent == pathlib.Path(stage)
assert vs12_adapter.VS2 is False
assert vs12_adapter.optolinkvs1 is not None

class SimulatedOwner:
    def __init__(self):
        self.writes = []
        self.pending = b""
        self.enq = False
    def reset_input_buffer(self):
        self.pending = b""
    def write(self, payload):
        payload = bytes(payload)
        self.writes.append(payload.hex())
        if payload == b"\x04":
            self.enq = True
        elif payload in (bytes.fromhex("01f700f804"),
                         bytes.fromhex("01c7f80404")):
            self.pending = bytes.fromhex("20c20003")
        elif payload == bytes.fromhex("01f700f808"):
            self.pending = bytes.fromhex("20c2000300000103")
        elif payload == bytes.fromhex("01c7f80804"):
            self.pending = bytes.fromhex("20c2000300000103")
        else:
            raise AssertionError("Unexpected serial output: " + payload.hex())
        return len(payload)
    def flush(self):
        pass
    def read(self, size):
        if self.enq:
            self.enq = False
            return b"\x05"
        return b""
    def read_all(self):
        payload = self.pending
        self.pending = b""
        return payload

port = SimulatedOwner()
vs12_adapter.optolinkvs1.last_comm = float("-inf")
records = []
for cmd in ("read;0x00f8;4", "gwgread;0xF8;4", "read;0x00f8;4",
            "gwgread;0xF8;8", "read;0x00f8;8"):
    value = requests_util.response_to_request(cmd, port)
    records.append(dict(command=cmd, status=value[0], payload=bytes(value[1]).hex(),
                        response=value[3]))
    assert value[0] == 1, (cmd, value)
    if cmd.endswith(";4"): assert bytes(value[1]).hex() == "20c20003"
    if cmd.endswith(";8"): assert bytes(value[1]).hex() == "20c2000300000103"
    # The caller in the real owner invokes olbreath which advances VS1 sync.
    vs12_adapter.reset_vs1sync()

wanted = ["04", "01f700f804",
          "04", "01c7f80404",
          "04", "01f700f804",
          "04", "01c7f80804",
          "04", "01f700f808"]
assert port.writes == wanted, (port.writes, wanted)

n = len(port.writes)
for cmd in ("gwgread;0x100;4", "gwgread;0xF0000;4",
            "gwgread;0xF8;9", "gwgread;0xFF;8", "gwgread;0xF8;4;2",
            "gwgread;0xF8;4;1;0"):
    row = requests_util.response_to_request(cmd, port)
    assert row[0] == 0xFD, (cmd, row)
assert len(port.writes) == n, "Invalid requests produced serial writes"
vs12_adapter.VS2 = True
try:
    row = requests_util.response_to_request("gwgread;0xF8;4", port)
    assert row[0] == 0xAF, row
    assert len(port.writes) == n
finally:
    vs12_adapter.VS2 = False
print(json.dumps({
    "result": "PASS", "simulation": "PRODUCTION_RUNTIME_COPIES_ONLY",
    "real_dispatcher": requests_util.__file__,
    "real_adapter": vs12_adapter.__file__,
    "wire": port.writes,
    "requests": records,
    "invalid_cases": 6, "p300_rejected": True,
    "port_ownership": "INJECTED_FAKE_SERIAL_ONLY",
    "controller_writes": 0
}, sort_keys=True))
'''


class RealRuntimeGWGEndToEnd(unittest.TestCase):
    @unittest.skipUnless(
        all((RUNTIME / x).is_file() for x in
            ("vs12_adapter.py", "requests_util.py", "optolinkvs1.py",
             "optolinkvs2.py", "settings_ini.py")),
        "Private runtime not mounted in generic CI"
    )
    def test_real_runtime_dispatcher_vs1_gwg_vs1_and_negative_cases(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gwg_stage_e2e", PATCH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
            with tempfile.TemporaryDirectory(prefix="gwg-real-owner-offline-") as path:
                stage = Path(path)
                for fname, digest in mod.BASE_SHA256.items():
                    source = (RUNTIME / fname).read_bytes()
                    self.assertEqual(hashlib.sha256(source).hexdigest(), digest)
                    (stage / fname).write_bytes(source)
                mod.stage(stage)
                py = (RUNTIME / "venv" / "bin" / "python")
                self.assertTrue(py.is_file())
                run = subprocess.run(
                    [str(py), "-c", TEST_SUBPROCESS, str(stage), str(RUNTIME)],
                    capture_output=True, text=True, timeout=15,
                    cwd=path,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
                )
                self.assertEqual(run.returncode, 0, run.stdout + "\n" + run.stderr)
                self.assertIn('"result": "PASS"', run.stdout)
                self.assertIn('"invalid_cases": 6', run.stdout)
                self.assertIn('"p300_rejected": true', run.stdout)
        finally:
            sys.modules.pop(spec.name, None)


if __name__ == "__main__":
    unittest.main()
