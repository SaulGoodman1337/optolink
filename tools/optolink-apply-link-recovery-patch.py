#!/usr/bin/env python3
"""Apply the Optolink link-recovery patch to optolink-splitter.

Problem (observed live on the WB2A/VDensHO1 host, Oct/Nov 2026):

1. Upstream main() gives up after ``max_restarts`` (5) failed re-starts and
   *returns*. The process then exits with status 0, so systemd
   ``Restart=on-failure`` never starts it again. If the boiler is unreachable
   while the splitter (re-)starts, init_protocol() fails five times within
   about a minute and the splitter stays dead until someone restarts it.
2. In VS1/KW mode a running splitter never re-opens the serial port. When the
   link is lost for a long time it only retries EOT/ENQ on the same file
   handle forever ("Timeout waiting for 0x05"). Restarting the process (fresh
   port open + init_protocol) recovered immediately in the field.

Fix (VS1 only for the watchdog, all modes for the restart loop):

- link watchdog: if no successful VS1 communication happened for
  LINK_LOST_RESTART_SECONDS, request the upstream soft re-start
  (utils.restart_event). That closes and re-opens the serial port, MQTT and
  TCP exactly like the upstream re-start path, then runs init_protocol().
- never give up: after ``max_restarts`` the re-start loop keeps retrying with
  an exponential back-off capped at RESTART_BACKOFF_MAX_SECONDS instead of
  exiting. Explicit shutdown (SIGTERM/SIGINT, poll-list errors) still exits.

The patch changes recovery control flow only. It adds no Optolink read/write
function, does not change any telegram, timing gap or olbreath, and keeps all
anchors used by tools/handover_acceleration/dispatcher_patch.py unique.
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
TARGET = "optolinkvs2_switch.py"
MARKER = "community-scripts: optolink link recovery"

# Blob of optolinkvs2_switch.py after upstream c1ee204a + phased poll
# scheduler 1.0.4 (the only layout this patch was validated against).
EXPECTED_INPUT_BLOBS = {
    "94c28cd4c59761e44e42149636ac6082129b787f",
}

# Anchors that tools/handover_acceleration/dispatcher_patch.py requires to be
# present exactly once. The recovery patch must not break the hybrid seam.
HYBRID_ANCHORS = (
    '                logger.info(f"{spr} protocol initialized")',
    'import requests_util\n',
    '                mod_mqtt.connect_mqtt()',
    '                        retcode,_,_ = vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)     # type: ignore',
    '            close_everything()',
    '                # let cpu take a breath if there was nothing to do',
    '        tcp_server.command_callback = do_special_command        # type: ignore',
)

GLOBALS_OLD = "    global num_restarts, num_vicon_tries, progr_exit_flag\n"
GLOBALS_NEW = (
    "    global num_restarts, num_vicon_tries, progr_exit_flag\n"
    "    global last_vs1_comm  # " + MARKER + "\n"
)

CONSTANTS_OLD = "num_vicon_tries = 0\nnum_restarts = 0\n"
CONSTANTS_NEW = (
    "num_vicon_tries = 0\n"
    "num_restarts = 0\n"
    "\n"
    "# " + MARKER + "\n"
    "# VS1: no successful Optolink response for this long -> re-open port + re-init.\n"
    "LINK_LOST_RESTART_SECONDS = 60\n"
    "# Never give up re-starting; back off up to this delay instead of exiting.\n"
    "RESTART_BACKOFF_MAX_SECONDS = 120\n"
    "\n"
    "def restart_backoff_delay(restarts:int, base:float, max_restarts:int,\n"
    "                          cap:float=RESTART_BACKOFF_MAX_SECONDS) -> float:\n"
    "    \"\"\"Delay before the next re-start; doubles after max_restarts, capped.\"\"\"\n"
    "    base = max(1.0, float(base))\n"
    "    if restarts < max_restarts:\n"
    "        return base\n"
    "    exponent = min(restarts - max_restarts + 1, 16)\n"
    "    return float(min(cap, base * (2 ** exponent)))\n"
)

MAINLOOP_OLD = '            logger.info("enter main loop")\n'
MAINLOOP_NEW = (
    '            logger.info("enter main loop")\n'
    "            # " + MARKER + ": init_protocol just succeeded\n"
    "            last_vs1_comm = time.monotonic()\n"
)

WATCHDOG_ANCHOR = "                # let cpu take a breath if there was nothing to do\n"
WATCHDOG = (
    "                # " + MARKER + ": VS1 link watchdog\n"
    "                if(settings.vs1protocol) and (time.monotonic() > last_vs1_comm + LINK_LOST_RESTART_SECONDS):\n"
    "                    logger.error(f\"Optolink link lost: no valid response for {LINK_LOST_RESTART_SECONDS}s \"\n"
    "                                 \"- re-open serial port and re-init protocol\")\n"
    "                    utils.restart_event.set()\n"
    "                    break\n"
    "\n"
)

FINALLY_OLD = (
    "            elif num_restarts >= settings.max_restarts:\n"
    "                logger.error(\"too many restarts - exit script\")\n"
    "                return\n"
    "            else:\n"
    "                logger.info(f\"waiting {settings.restart_delay}s before re-start...\")\n"
    "                time.sleep(settings.restart_delay)\n"
)
FINALLY_NEW = (
    "            else:\n"
    "                # " + MARKER + ": never exit while the boiler is away\n"
    "                delay = restart_backoff_delay(num_restarts, settings.restart_delay, settings.max_restarts)\n"
    "                if num_restarts >= settings.max_restarts:\n"
    "                    logger.warning(f\"Optolink still not available after {num_restarts} re-starts \"\n"
    "                                   f\"- keep trying, next attempt in {delay:.0f}s\")\n"
    "                else:\n"
    "                    logger.info(f\"waiting {delay:.0f}s before re-start...\")\n"
    "                time.sleep(delay)\n"
)

REPLACEMENTS = (
    ("constants", CONSTANTS_OLD, CONSTANTS_NEW),
    ("globals", GLOBALS_OLD, GLOBALS_NEW),
    ("main loop entry", MAINLOOP_OLD, MAINLOOP_NEW),
    ("watchdog", WATCHDOG_ANCHOR, WATCHDOG + WATCHDOG_ANCHOR),
    ("restart back-off", FINALLY_OLD, FINALLY_NEW),
)


class PatchError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def write_text_preserve(path: Path, text: str) -> None:
    st = path.stat()
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".linkrec.", dir=str(path.parent))
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


def patch_switch(text: str) -> str:
    if MARKER in text:
        return text
    # Upstream ships optolinkvs2_switch.py with CRLF line endings. Patch on a
    # LF view and restore the original (uniform) line ending afterwards.
    crlf = "\r\n" in text
    if crlf:
        if text.count("\n") != text.count("\r\n"):
            raise PatchError("mixed line endings not supported")
        text = text.replace("\r\n", "\n")
    out = text
    for name, old, new in REPLACEMENTS:
        if out.count(old) != 1:
            raise PatchError(f"unexpected upstream layout ({name}): anchor count {out.count(old)}")
        out = out.replace(old, new, 1)
    for anchor in HYBRID_ANCHORS:
        if text.count(anchor) == 1 and out.count(anchor) != 1:
            raise PatchError("hybrid dispatcher anchor would no longer be unique")
    compile(out, TARGET, "exec")
    return out.replace("\n", "\r\n") if crlf else out


def state_for(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    raw = path.read_bytes()
    if MARKER.encode() in raw:
        return "PATCHED"
    blob = git_blob_sha(raw)
    if blob in EXPECTED_INPUT_BLOBS:
        return "BASE"
    return f"UNKNOWN blob={blob}"


def apply(root: Path) -> None:
    path = root / TARGET
    state = state_for(path)
    if state == "PATCHED":
        print(f"{TARGET}: already patched")
        print("RESULT=PASS")
        return
    if state != "BASE":
        raise PatchError(f"{TARGET}: refusing to patch unvalidated layout ({state})")

    original = read_text(path)
    patched = patch_switch(original)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{TARGET}.bak-linkrec-{stamp}")
    shutil.copy2(path, backup)
    try:
        write_text_preserve(path, patched)
        py_compile.compile(str(path), doraise=True)
        if MARKER not in read_text(path):
            raise PatchError("post-patch marker missing")
    except Exception:
        shutil.copy2(backup, path)
        raise
    print("BACKUP=" + str(backup))
    print(f"{TARGET} blob={git_blob_sha(path.read_bytes())}")
    print("RESULT=PASS")


def self_test() -> int:
    import unittest

    sample = (
        "import requests_util\n"
        "import utils\n"
        "import time\n"
        "num_vicon_tries = 0\n"
        "num_restarts = 0\n"
        "last_vs1_comm = 0\n"
        "def main():\n"
        "    global num_restarts, num_vicon_tries, progr_exit_flag\n"
        "    while True:\n"
        "        try:\n"
        "            logger.info(\"enter main loop\")\n"
        "            while not utils.restart_event.is_set():\n"
        "                did = False\n"
        "                # let cpu take a breath if there was nothing to do\n"
        "                time.sleep(0.005)\n"
        "        finally:\n"
        "            close_everything()\n"
        "            if utils.shutdown_event.is_set():\n"
        "                return\n"
        + FINALLY_OLD
    )

    class Tests(unittest.TestCase):
        def test_patch_applies_and_is_idempotent(self):
            out = patch_switch(sample)
            self.assertIn(MARKER, out)
            self.assertNotIn("too many restarts - exit script", out)
            self.assertIn("utils.restart_event.set()", out)
            self.assertIn("global last_vs1_comm", out)
            self.assertEqual(patch_switch(out), out)

        def test_crlf_roundtrip(self):
            crlf = sample.replace("\n", "\r\n")
            out = patch_switch(crlf)
            self.assertIn(MARKER, out)
            self.assertEqual(out.count("\n"), out.count("\r\n"))
            self.assertEqual(out.replace("\r\n", "\n"), patch_switch(sample))

        def test_layout_change_fails_closed(self):
            with self.assertRaises(PatchError):
                patch_switch(sample.replace("too many restarts", "other"))

        def test_backoff(self):
            ns = {}
            exec(CONSTANTS_NEW, ns)
            f = ns["restart_backoff_delay"]
            self.assertEqual([f(n, 10, 5) for n in range(1, 11)],
                             [10, 10, 10, 10, 20, 40, 80, 120, 120, 120])
            self.assertEqual(f(10**6, 10, 5), 120)
            self.assertEqual(f(0, 0, 5), 1.0)

        def test_hybrid_anchors_stay_unique(self):
            out = patch_switch(sample)
            for anchor in HYBRID_ANCHORS:
                self.assertLessEqual(out.count(anchor), 1)
            self.assertEqual(out.count(WATCHDOG_ANCHOR), 1)

        def test_git_blob(self):
            self.assertEqual(git_blob_sha(b"test\n"),
                             "9daeafb9864cf43055ae93beb0afd6c7d144bfa4")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("LINK_RECOVERY_TESTS=6/6")
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

    print(f"link-recovery patch {VERSION}")
    print(f"{TARGET}: {state_for(args.root / TARGET)}")
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
