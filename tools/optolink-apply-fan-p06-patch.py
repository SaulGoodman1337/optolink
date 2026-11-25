#!/usr/bin/env python3
"""Hook fan_p06.py (real GFA P06 fan speed via short VS1 windows) into the splitter.

Only active in permanent P300 operation (settings.vs1protocol = False and no
Vitoconnect pass-through). While the flame is on, fan_p06 switches the link
for a few seconds to VS1, reads GFA P80/P06/P09/P87 (read-only 0x6B) and
returns to P300. See config/optolink-splitter/fan_p06.py.

Changes in optolinkvs2_switch.py (after the pump guard patch):
1. Import fan_p06 in try/except (a missing module never breaks the splitter).
2. After the pump guard init: get/rebind the fan_p06 singleton to the new
   serial port; the flame state comes from the pump guard (no extra reads).
3. In the main loop, after the pump guard tick: fan_p06.tick() (one telegram
   or one complete VS1 window), followed by olbreath(retcode).

Must run after the pump guard patcher (pinned to its output blob).
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile
import time

VERSION = "1.0.0"
ROOT = Path("/opt/optolink")
MARKER = "community-scripts: fan p06"

# optolinkvs2_switch.py after upstream c1ee204a + phased scheduler 1.0.4 +
# link recovery 1.0.0 + p300 runtime 1.0.0 + pump guard 1.0.0.
EXPECTED_INPUT_BLOBS = {
    "optolinkvs2_switch.py": {"0b5eb10c4f8f789f6cfd9afa9f934eea03a0c387"},
}

HYBRID_ANCHORS = (
    '                logger.info(f"{spr} protocol initialized")',
    'import requests_util\n',
    '                mod_mqtt.connect_mqtt()',
    '                        retcode,_,_ = vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)     # type: ignore',
    '            close_everything()',
    '                # let cpu take a breath if there was nothing to do',
    '        tcp_server.command_callback = do_special_command        # type: ignore',
    "vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)",
)

SWITCH_REPLACEMENTS = (
    (
        "import",
        "    print(f\"pump_guard not available: {_pg_exc}\")\n",
        "    print(f\"pump_guard not available: {_pg_exc}\")\n"
        "try:  # " + MARKER + "\n"
        "    import fan_p06\n"
        "except Exception as _fp_exc:  # never break the splitter\n"
        "    fan_p06 = None\n"
        "    print(f\"fan_p06 not available: {_fp_exc}\")\n",
    ),
    (
        "init",
        "                    logger.warning(f\"pump_guard init failed: {_pg_exc}\")\n"
        "                    pump_guard_obj = None\n",
        "                    logger.warning(f\"pump_guard init failed: {_pg_exc}\")\n"
        "                    pump_guard_obj = None\n"
        "            # " + MARKER + ": (re)bind the VS1-window fan reader (P300 only)\n"
        "            fan_p06_obj = None\n"
        "            if(fan_p06 is not None) and (not settings.vs1protocol) and (serVitoConnnect is None):\n"
        "                try:\n"
        "                    _fp_flame = None\n"
        "                    if(pump_guard_obj is not None):\n"
        "                        _fp_flame = (lambda _g=pump_guard_obj: _g.logic.flame\n"
        "                            if (time.monotonic() - _g.logic.ts.get(\"gfa\", -1e9)) <= 5.0 else None)\n"
        "                    fan_p06_obj = fan_p06.get(settings, logger, fan_p06.Backend(serOptolink), _fp_flame)\n"
        "                except Exception as _fp_exc:\n"
        "                    logger.warning(f\"fan_p06 init failed: {_fp_exc}\")\n"
        "                    fan_p06_obj = None\n",
    ),
    (
        "tick",
        "                # community-scripts: p300 runtime: P300 keep-alive when idle\n",
        "                # " + MARKER + ": one telegram or one complete VS1 window\n"
        "                if(fan_p06_obj is not None):\n"
        "                    rc_fan = fan_p06_obj.tick()\n"
        "                    if(rc_fan is not None):\n"
        "                        olbreath(rc_fan)\n"
        "                        did_secodary_request = True\n"
        "\n"
        "                # community-scripts: p300 runtime: P300 keep-alive when idle\n",
    ),
)

TARGETS = {
    "optolinkvs2_switch.py": SWITCH_REPLACEMENTS,
}


class PatchError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def patch_text(rel: str, text: str) -> str:
    if MARKER in text:
        return text
    crlf = "\r\n" in text
    if crlf:
        if text.count("\n") != text.count("\r\n"):
            raise PatchError(f"{rel}: mixed line endings not supported")
        text = text.replace("\r\n", "\n")
    out = text
    for name, old, new in TARGETS[rel]:
        if out.count(old) != 1:
            raise PatchError(f"{rel}: unexpected layout ({name}): anchor count {out.count(old)}")
        out = out.replace(old, new, 1)
    if rel == "optolinkvs2_switch.py":
        for anchor in HYBRID_ANCHORS:
            if text.count(anchor) == 1 and out.count(anchor) != 1:
                raise PatchError("hybrid dispatcher anchor would no longer be unique")
    compile(out, rel, "exec")
    return out.replace("\n", "\r\n") if crlf else out


def state_for(path: Path, rel: str) -> str:
    if not path.exists():
        return "MISSING"
    raw = path.read_bytes()
    if MARKER.encode() in raw:
        return "PATCHED"
    blob = git_blob_sha(raw)
    if blob in EXPECTED_INPUT_BLOBS[rel]:
        return "BASE"
    return f"UNKNOWN blob={blob}"


def write_text_preserve(path: Path, text: str) -> None:
    st = path.stat()
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".fanp06.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except PermissionError:
            if os.geteuid() == 0:
                raise
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply(root: Path) -> None:
    states = {rel: state_for(root / rel, rel) for rel in TARGETS}
    bad = {k: v for k, v in states.items() if v not in ("BASE", "PATCHED")}
    if bad:
        raise PatchError(f"refusing unvalidated layout: {bad}")
    todo = [rel for rel, st in states.items() if st == "BASE"]
    if not todo:
        print("all targets already patched")
        print("RESULT=PASS")
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    patched = {rel: patch_text(rel, (root / rel).read_bytes().decode("utf-8")) for rel in todo}
    backups = {}
    try:
        for rel in todo:
            path = root / rel
            backups[rel] = path.with_name(f"{rel}.bak-fanp06-{stamp}")
            shutil.copy2(path, backups[rel])
            write_text_preserve(path, patched[rel])
            py_compile.compile(str(path), doraise=True)
    except Exception:
        for rel, backup in backups.items():
            shutil.copy2(backup, root / rel)
        raise
    for rel in todo:
        print(f"BACKUP={backups[rel]}")
        print(f"{rel} blob={git_blob_sha((root / rel).read_bytes())}")
    print("RESULT=PASS")


def self_test() -> int:
    import unittest

    switch = (
        "import time\n"
        "try:\n"
        "    pass\n"
        "except Exception as _pg_exc:\n"
        + SWITCH_REPLACEMENTS[0][1]
        + "def main():\n"
        "    if True:\n"
        "        if True:\n"
        "            if True:\n"
        "                try:\n"
        "                    pass\n"
        "                except Exception as _pg_exc:\n"
        + SWITCH_REPLACEMENTS[1][1]
        + "            while True:\n"
        + SWITCH_REPLACEMENTS[2][1]
        + "                    break\n"
    ).replace("\n", "\r\n")

    class Tests(unittest.TestCase):
        def test_patch_crlf_idempotent(self):
            out = patch_text("optolinkvs2_switch.py", switch)
            self.assertIn(MARKER, out)
            self.assertEqual(out.count("\n"), out.count("\r\n"))
            self.assertEqual(patch_text("optolinkvs2_switch.py", out), out)

        def test_tick_before_keepalive_and_guarded(self):
            lf = patch_text("optolinkvs2_switch.py", switch).replace("\r\n", "\n")
            self.assertLess(lf.index("fan_p06_obj.tick()"), lf.index("P300 keep-alive when idle"))
            self.assertIn("(not settings.vs1protocol) and (serVitoConnnect is None)", lf)
            self.assertIn("except Exception as _fp_exc:  # never break the splitter", lf)

        def test_layout_change_fails_closed(self):
            with self.assertRaises(PatchError):
                patch_text("optolinkvs2_switch.py", switch.replace("pump_guard not available", "x"))

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if result.wasSuccessful():
        print("FAN_P06_PATCH_TESTS=3/3")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    print(f"fan p06 patch {VERSION}")
    for rel in TARGETS:
        print(f"{rel}: {state_for(args.root / rel, rel)}")
    if not args.apply:
        print("RESULT=CHECK_ONLY")
        return 0
    if args.root == ROOT and os.geteuid() != 0:
        print("ERROR: --apply requires root", file=sys.stderr)
        return 1
    try:
        apply(args.root)
        return 0
    except Exception as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
