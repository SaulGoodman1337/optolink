#!/usr/bin/env python3
"""Make the patched optolink-splitter safe for permanent P300 (VS2) operation.

Production normally runs VS1. Permanent P300 is needed for the inverted pump
override (physical RAM writes exist only in P300). Upstream supports VS2
natively; our local patches were written for VS1 and need three adjustments:

1. Link watchdog for both protocols: any valid response (retcode <= 0x03)
   refreshes the link timestamp, and the 60 s link-lost watchdog from the
   link-recovery patch now also triggers in P300. VS1 behaviour is unchanged
   (VS1 already refreshed the timestamp in exactly this branch).
2. P300 keep-alive: if the link has been idle for P300_KEEPALIVE_SECONDS, read
   the device identity 0x00F8 (the same datapoint VS1 uses for keep-alive).
3. GFA items: "gfa:" poll items use VS1-only GFA_READ 0x6B. The WB2A rejects
   GFA via P300 (live finding 2026-10-08), so under P300 these items are left
   out of the poll list instead of failing every cycle.

No new write function, no RAM access, no telegram change in VS1 mode.
Must run after the link-recovery patcher (pinned to its output blob).
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
MARKER = "community-scripts: p300 runtime"

# optolinkvs2_switch.py after upstream c1ee204a + phased scheduler 1.0.4 +
# link recovery 1.0.0; c_polllist.py after the phased scheduler.
EXPECTED_INPUT_BLOBS = {
    "optolinkvs2_switch.py": {"fdf4d66cea59315ff75485d9b3f636a1bb0e3221"},
    "c_polllist.py": {"f42ad5be08ea26c6947f97d346c7c11adb40c364"},
}

HYBRID_ANCHORS = (
    '                logger.info(f"{spr} protocol initialized")',
    'import requests_util\n',
    '                mod_mqtt.connect_mqtt()',
    '                        retcode,_,_ = vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)     # type: ignore',
    '            close_everything()',
    '                # let cpu take a breath if there was nothing to do',
    '        tcp_server.command_callback = do_special_command        # type: ignore',
)

SWITCH_REPLACEMENTS = (
    (
        "olbreath success",
        "        # success, err msg\n"
        "        if(settings.vs1protocol):\n"
        "            last_vs1_comm = time.monotonic()\n"
        "            vs12_adapter.reset_vs1sync()\n"
        "        time.sleep(settings.olbreath)\n",
        "        # success, err msg\n"
        "        # " + MARKER + ": any valid response proves the link (VS1 and P300)\n"
        "        last_vs1_comm = time.monotonic()\n"
        "        if(settings.vs1protocol):\n"
        "            vs12_adapter.reset_vs1sync()\n"
        "        time.sleep(settings.olbreath)\n",
    ),
    (
        "constants",
        "LINK_LOST_RESTART_SECONDS = 60\n",
        "LINK_LOST_RESTART_SECONDS = 60\n"
        "# " + MARKER + ": idle time before a P300 identity keep-alive read\n"
        "P300_KEEPALIVE_SECONDS = 5.0\n",
    ),
    (
        "watchdog",
        "                # community-scripts: optolink link recovery: VS1 link watchdog\n"
        "                if(settings.vs1protocol) and (time.monotonic() > last_vs1_comm + LINK_LOST_RESTART_SECONDS):\n",
        "                # " + MARKER + ": P300 keep-alive when idle\n"
        "                if(not settings.vs1protocol) and (serVitoConnnect is None) and (time.monotonic() > last_vs1_comm + P300_KEEPALIVE_SECONDS):\n"
        "                    rc_keepalive,_,_ = vs12_adapter.read_datapoint_ext(0x00F8, 2, serOptolink)  # type: ignore\n"
        "                    olbreath(rc_keepalive)\n"
        "                    did_secodary_request = True\n"
        "\n"
        "                # community-scripts: optolink link recovery: link watchdog (" + MARKER + ": VS1 and P300)\n"
        "                if(time.monotonic() > last_vs1_comm + LINK_LOST_RESTART_SECONDS):\n",
    ),
)

POLLLIST_REPLACEMENTS = (
    (
        "gfa filter",
        "            for item in listmodule.poll_items:\n"
        "                new_item = []\n",
        "            # " + MARKER + ": GFA_READ 0x6B is VS1-only; the WB2A rejects GFA via P300\n"
        "            gfa_skipped = 0\n"
        "            for item in listmodule.poll_items:\n"
        "                if (not settings.vs1protocol) and any(\n"
        "                        isinstance(x, str) and x.lower().startswith('gfa:') for x in item[1:]):\n"
        "                    gfa_skipped += 1\n"
        "                    continue\n"
        "                new_item = []\n",
    ),
    (
        "gfa log",
        '            logger.info(f"poll_list made, {self.num_items} items")\n',
        '            logger.info(f"poll_list made, {self.num_items} items")\n'
        "            if gfa_skipped:\n"
        '                logger.warning(f"P300: {gfa_skipped} VS1-only GFA poll items disabled")\n',
    ),
)

TARGETS = {
    "optolinkvs2_switch.py": SWITCH_REPLACEMENTS,
    "c_polllist.py": POLLLIST_REPLACEMENTS,
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
        for anchor in HYBRID_ANCHORS + ("vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)",):
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
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".p300rt.", dir=str(path.parent))
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
            backups[rel] = path.with_name(f"{rel}.bak-p300rt-{stamp}")
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
        "LINK_LOST_RESTART_SECONDS = 60\n"
        "def olbreath(retcode):\n"
        "    global last_vs1_comm\n"
        "    if(retcode <= 0x03):\n"
        + SWITCH_REPLACEMENTS[0][1]
        + "def loop():\n"
        "            while True:\n"
        + SWITCH_REPLACEMENTS[2][1]
        + "                    break\n"
    ).replace("\n", "\r\n")
    polllist = (
        "def make_list(self, listmodule):\n"
        "        try:\n"
        + POLLLIST_REPLACEMENTS[0][1]
        + "                pass\n"
        + POLLLIST_REPLACEMENTS[1][1]
        + "        except Exception:\n"
        "            pass\n"
    )

    class Tests(unittest.TestCase):
        def test_switch_patch_crlf_idempotent(self):
            out = patch_text("optolinkvs2_switch.py", switch)
            self.assertIn(MARKER, out)
            self.assertEqual(out.count("\n"), out.count("\r\n"))
            self.assertEqual(patch_text("optolinkvs2_switch.py", out), out)
            lf = out.replace("\r\n", "\n")
            self.assertIn("if(time.monotonic() > last_vs1_comm + LINK_LOST_RESTART_SECONDS):", lf)
            self.assertNotIn("if(settings.vs1protocol) and (time.monotonic() > last_vs1_comm", lf)
            self.assertIn("P300_KEEPALIVE_SECONDS = 5.0", lf)

        def test_vs1_reset_sync_kept(self):
            lf = patch_text("optolinkvs2_switch.py", switch).replace("\r\n", "\n")
            self.assertIn("        if(settings.vs1protocol):\n            vs12_adapter.reset_vs1sync()\n", lf)

        def test_polllist_patch(self):
            out = patch_text("c_polllist.py", polllist)
            self.assertIn("gfa_skipped += 1", out)
            self.assertEqual(patch_text("c_polllist.py", out), out)

        def test_gfa_predicate(self):
            pred = lambda item: any(isinstance(x, str) and x.lower().startswith('gfa:') for x in item[1:])
            self.assertTrue(pred(("FAST", "geblaesedrehzahl_gfa_p06", 0x4006, 1, "gfa:30", False)))
            self.assertFalse(pred(("FAST", "gfa_kennung", 0x7650, 1, 1, False)))
            self.assertFalse(pred(("FAST", "brenner_flamme", 0x55D3, 9, "b:5:5:0x20", "bool", False)))

        def test_layout_change_fails_closed(self):
            with self.assertRaises(PatchError):
                patch_text("c_polllist.py", polllist.replace("new_item = []", "x = []"))

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if result.wasSuccessful():
        print("P300_RUNTIME_TESTS=5/5")
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
    print(f"p300 runtime patch {VERSION}")
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
