#!/usr/bin/env python3
"""Apply the validated phased poll-scheduler patch to optolink-splitter.

Goals for the VDensHO1/WB2A profile:
- spread NORMAL/DIAG/SLOW/RARE reads across their period instead of bunching
  every member of a group into one long poll cycle;
- preserve one initial full snapshot on process start;
- make ONCE truly startup-only for the lifetime of the splitter process;
- keep completed ONCE disabled across forcepoll and reloadpoll;
- keep explicit per-datapoint forced readback working unchanged;
- make forcepoll refresh all regular groups, but never completed ONCE items.

This patch changes scheduling only. It does not add any Optolink read/write
function and does not change olbreath.
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

VERSION = "1.0.4"
ROOT = Path("/opt/optolink")

BASE_BLOBS = {
    "c_polllist.py": "2502f9b7bf2b4bd2b218286e135b9694191f970b",
    "optolinkvs2_switch.py": "1fae36baae1c2ef264906c8eca76ef15c5152974",
}

MARKERS = {
    "c_polllist.py": "community-scripts: phased group poll scheduler",
    "optolinkvs2_switch.py": "community-scripts: phased poll scheduler runtime",
}


class PatchError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def write_text_preserve(path: Path, text: str) -> None:
    st = path.stat()
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".poll.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, st.st_mode & 0o7777)
        os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def patch_c_polllist(text: str) -> str:
    if MARKERS["c_polllist.py"] in text:
        return text
    nl = newline_of(text)

    old = nl.join([
        "        self.items = []",
        "        self.cycle_groups = {}",
        "        self.num_items = 0",
    ])
    new = nl.join([
        "        self.items = []",
        "        # community-scripts: phased group poll scheduler",
        "        self.item_phases = []",
        "        self.cycle_groups = {}",
        "        self.num_items = 0",
    ])
    if old not in text:
        raise PatchError("c_polllist.py __init__ marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "    def make_list(self, reload = False):",
        "        self.items = []",
        "        self.cycle_groups = {}",
        "        self.num_items = 0",
    ])
    new = nl.join([
        "    def make_list(self, reload = False):",
        "        self.items = []",
        "        self.item_phases = []",
        "        self.cycle_groups = {}",
        "        self.num_items = 0",
    ])
    if old not in text:
        raise PatchError("c_polllist.py make_list reset marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "            # apply poll list",
        "            #self.items = listmodule.poll_items",
        "            for item in listmodule.poll_items:",
    ])
    new = nl.join([
        "            # apply poll list",
        "            #self.items = listmodule.poll_items",
        "            # Each recurring group gets a deterministic per-transaction",
        "            # phase. This spreads slow groups across cycles instead of",
        "            # creating one large burst every Nth cycle.",
        "            group_tx_ordinal = {}",
        "            last_tx_key = None",
        "            last_was_bytebit = False",
        "            last_phase = 0",
        "            for item in listmodule.poll_items:",
    ])
    if old not in text:
        raise PatchError("c_polllist.py poll-list loop marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "                # append to poll items",
        "                self.items.append(new_tuple)",
        "",
        "            self.num_items = len(self.items)",
    ])
    new = nl.join([
        "                # append to poll items",
        "                self.items.append(new_tuple)",
        "",
        "                # Assign one phase per physical transaction. Consecutive",
        "                # byte/bit filters of the same address/length share the",
        "                # phase because do_poll_item reuses the same response.",
        "                group_key = new_tuple[0]",
        "                period = self.cycle_groups[group_key]",
        "                is_bytebit = (",
        "                    len(new_tuple) > 4",
        "                    and isinstance(new_tuple[4], str)",
        "                    and new_tuple[4].lower().startswith('b:')",
        "                )",
        "                tx_key = (group_key, new_tuple[2], new_tuple[3])",
        "                continuation = is_bytebit and last_was_bytebit and tx_key == last_tx_key",
        "                if period > 1:",
        "                    if continuation:",
        "                        phase = last_phase",
        "                    else:",
        "                        ordinal = group_tx_ordinal.get(group_key, 0)",
        "                        phase = ordinal % period",
        "                        group_tx_ordinal[group_key] = ordinal + 1",
        "                else:",
        "                    phase = 0",
        "                self.item_phases.append(phase)",
        "                last_tx_key = tx_key",
        "                last_was_bytebit = is_bytebit",
        "                last_phase = phase",
        "",
        "            self.num_items = len(self.items)",
    ])
    if old not in text:
        raise PatchError("c_polllist.py append marker not found")
    return text.replace(old, new, 1)


def patch_switch(text: str) -> str:
    nl = newline_of(text)
    failsoft_marker = "community-scripts: fail-soft poll value conversion"

    def add_failsoft_guard(src: str) -> str:
        if failsoft_marker in src:
            return src
        old = nl.join([
            "    except Exception as e:",
            '        logger.error(f"Error do_poll_item {poll_pointer}, {item}: {e}")',
            "        raise",
        ])
        new = nl.join([
            "    except (UnicodeError, ValueError, IndexError, OverflowError) as e:",
            "        # community-scripts: fail-soft poll value conversion",
            "        # A malformed payload or formatter mismatch invalidates only",
            "        # this datapoint. Transport/serial exceptions still fall",
            "        # through to the original hard recovery path below.",
            "        bad_item = locals().get('item', '<unavailable>')",
            "        logger.warning(",
            '            f"Skipping malformed poll value {poll_pointer}, {bad_item}: "',
            '            f"{type(e).__name__}: {e}"',
            "        )",
            "        return 0xFD",
            "    except Exception as e:",
            '        logger.error(f"Error do_poll_item {poll_pointer}, {item}: {e}")',
            "        raise",
        ])
        if old not in src:
            raise PatchError("switch poll exception marker not found")
        return src.replace(old, new, 1)

    if MARKERS["optolinkvs2_switch.py"] in text:
        return add_failsoft_guard(text)

    old = nl.join([
        "force_poll_flag = False",
        "reload_poll_flag = False",
        "",
        "num_vicon_tries = 0",
    ])
    new = nl.join([
        "force_poll_flag = False",
        "reload_poll_flag = False",
        "# community-scripts: phased poll scheduler runtime",
        "force_poll_all_regular = False",
        "startup_once_complete = False",
        "",
        "num_vicon_tries = 0",
    ])
    if old not in text:
        raise PatchError("switch global marker not found")
    text = text.replace(old, new, 1)

    old = "    global poll_pointer" + nl
    new = "    global poll_pointer, force_poll_all_regular, startup_once_complete" + nl
    if old not in text:
        raise PatchError("switch do_poll_item global marker not found")
    text = text.replace(old, new, 1)

    old = (
        "            if(item_index is None) and ((item_cycle < 0) or "
        "((item_cycle > 0) and (poll_cycle % item_cycle != 0)) or "
        "((item_cycle == 0) and (poll_cycle != 0))):"
    )
    new = nl.join([
        "            item_phase = (",
        "                poll_list.item_phases[list_index]",
        "                if list_index < len(poll_list.item_phases) else 0",
        "            )",
        "            startup_seed = (not startup_once_complete) and (poll_cycle == 0)",
        "",
        "            if item_cycle < 0:",
        "                item_due = False",
        "            elif item_cycle == 0:",
        "                # True ONCE semantics: only during the first process-start cycle.",
        "                item_due = startup_seed",
        "            elif force_poll_all_regular:",
        "                # Explicit full refresh excludes completed ONCE items.",
        "                item_due = True",
        "            elif startup_seed:",
        "                # Preserve the historical complete initial snapshot.",
        "                item_due = True",
        "            else:",
        "                item_due = (poll_cycle % item_cycle) == item_phase",
        "",
        "            if(item_index is None) and (not item_due):",
    ])
    if old not in text:
        raise PatchError("switch due-condition marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "    global mod_mqtt",
        "    global poll_pointer, poll_cycle",
        "    global force_poll_flag, reload_poll_flag",
    ])
    new = nl.join([
        "    global mod_mqtt",
        "    global poll_pointer, poll_cycle",
        "    global force_poll_flag, reload_poll_flag",
        "    global force_poll_all_regular, startup_once_complete",
    ])
    if old not in text:
        raise PatchError("switch main globals marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "                            # force poll including onceonlies",
        "                            if force_poll_flag:",
        "                                poll_pointer = 0",
        "                                poll_cycle = 0",
        "                                force_poll_flag = False",
    ])
    new = nl.join([
        "                            # Force all recurring groups once. Completed",
        "                            # ONCE/startup-only items remain excluded.",
        "                            if force_poll_flag:",
        "                                poll_pointer = 0",
        "                                force_poll_all_regular = True",
        "                                force_poll_flag = False",
    ])
    if old not in text:
        raise PatchError("switch forcepoll marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "                            # reload poll list, including onceonlies",
        "                            if reload_poll_flag:",
        "                                poll_list.make_list(reload=True)",
        "                                if(len(poll_data) != poll_list.num_items):          # type: ignore",
        "                                    poll_data = [None] * poll_list.num_items",
        "                                publish_stats()",
        "                                poll_pointer = 0",
        "                                poll_cycle = 0",
        "                                reload_poll_flag = False",
    ])
    new = nl.join([
        "                            # Reload profile without replaying completed ONCE items.",
        "                            if reload_poll_flag:",
        "                                poll_list.make_list(reload=True)",
        "                                if startup_once_complete and poll_list.cycle_groups.get('ONCE') == 0:",
        "                                    poll_list.cycle_groups['ONCE'] = -1",
        "                                if(len(poll_data) != poll_list.num_items):          # type: ignore",
        "                                    poll_data = [None] * poll_list.num_items",
        "                                publish_stats()",
        "                                poll_pointer = 0",
        "                                reload_poll_flag = False",
    ])
    if old not in text:
        raise PatchError("switch reloadpoll marker not found")
    text = text.replace(old, new, 1)

    old = nl.join([
        "                                    # poll cycle control",
        "                                    poll_cycle += 1",
    ])
    new = nl.join([
        "                                    # Complete startup-only semantics before",
        "                                    # advancing the recurring phased schedule.",
        "                                    if not startup_once_complete:",
        "                                        startup_once_complete = True",
        "                                        if poll_list.cycle_groups.get('ONCE') == 0:",
        "                                            poll_list.cycle_groups['ONCE'] = -1",
        "                                        logger.info('startup-only ONCE poll group completed')",
        "                                    if force_poll_all_regular:",
        "                                        force_poll_all_regular = False",
        "",
        "                                    # poll cycle control",
        "                                    poll_cycle += 1",
    ])
    if old not in text:
        raise PatchError("switch cycle-complete marker not found")
    text = text.replace(old, new, 1)
    return add_failsoft_guard(text)


PATCHERS = {
    "c_polllist.py": patch_c_polllist,
    "optolinkvs2_switch.py": patch_switch,
}


def state_for(path: Path, rel: str) -> str:
    if not path.is_file():
        return "missing"
    data = path.read_bytes()
    text = data.decode("utf-8")
    blob = git_blob_sha(data)
    if blob == BASE_BLOBS[rel]:
        return "base"
    if MARKERS[rel] in text:
        return "patched"
    return "unexpected:" + blob


def apply(root: Path) -> Path:
    states = {rel: state_for(root / rel, rel) for rel in PATCHERS}
    bad = {k: v for k, v in states.items() if v not in ("base", "patched")}
    if bad:
        raise PatchError("refusing unexpected scheduler runtime files: " + repr(bad))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = Path("/root") / f"optolink-phased-poll-backup-{stamp}-{os.getpid()}"
    if root != ROOT:
        backup = root / ".phased-poll-test-backup"
    backup.mkdir(mode=0o700, parents=True, exist_ok=False)

    originals = {}
    patched_texts = {}
    changed = []

    # Build and syntax-check the complete patch set before writing anything.
    for rel, patcher in PATCHERS.items():
        path = root / rel
        shutil.copy2(path, backup / rel)
        original = read_text(path)
        originals[rel] = original
        patched = patcher(original)
        compile(patched, str(path), "exec")
        patched_texts[rel] = patched
        if patched != original:
            changed.append(rel)

    try:
        for rel in changed:
            write_text_preserve(root / rel, patched_texts[rel])

        for rel in PATCHERS:
            py_compile.compile(str(root / rel), doraise=True)
            if MARKERS[rel] not in read_text(root / rel):
                raise PatchError(f"post-patch marker missing in {rel}")
    except Exception:
        # Transactional rollback: never leave only half of the scheduler patch.
        for rel in PATCHERS:
            shutil.copy2(backup / rel, root / rel)
        raise

    print("PATCHED_FILES=" + ",".join(changed))
    print("BACKUP=" + str(backup))
    for rel in PATCHERS:
        print(f"{rel} blob={git_blob_sha((root / rel).read_bytes())}")
    print("RESULT=PASS")
    return backup


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_poll_list_patch(self):
            src = """class cPollList:
    def __init__(self):
        self.items = []
        self.cycle_groups = {}
        self.num_items = 0
        self.module_date = "0"

    def make_list(self, reload = False):
        self.items = []
        self.cycle_groups = {}
        self.num_items = 0
        self.module_date = "0"
        try:
            # apply poll list
            #self.items = listmodule.poll_items
            for item in listmodule.poll_items:
                new_item = []
                # make tuple
                new_tuple = tuple(new_item)
                # append to poll items
                self.items.append(new_tuple)

            self.num_items = len(self.items)
"""
            out = patch_c_polllist(src)
            self.assertIn("self.item_phases = []", out)
            self.assertIn("group_tx_ordinal = {}", out)
            self.assertIn("continuation = is_bytebit", out)

        def test_switch_patch(self):
            # Synthetic source keeps the exact indentation of the real upstream
            # markers patch_switch() intentionally matches fail-closed.
            src = """force_poll_flag = False
reload_poll_flag = False

num_vicon_tries = 0

def do_poll_item(poll_data, ser, item_index=None):
    global poll_pointer
    while(True):
        list_index = item_index if item_index is not None else poll_pointer
        item = poll_list.items[list_index]
        item_cycle = poll_list.cycle_groups[item[0]]

            if(item_index is None) and ((item_cycle < 0) or ((item_cycle > 0) and (poll_cycle % item_cycle != 0)) or ((item_cycle == 0) and (poll_cycle != 0))):
                pass

def main():
    global mod_mqtt
    global poll_pointer, poll_cycle
    global force_poll_flag, reload_poll_flag
                            # force poll including onceonlies
                            if force_poll_flag:
                                poll_pointer = 0
                                poll_cycle = 0
                                force_poll_flag = False
                            # reload poll list, including onceonlies
                            if reload_poll_flag:
                                poll_list.make_list(reload=True)
                                if(len(poll_data) != poll_list.num_items):          # type: ignore
                                    poll_data = [None] * poll_list.num_items
                                publish_stats()
                                poll_pointer = 0
                                poll_cycle = 0
                                reload_poll_flag = False
                                    # poll cycle control
                                    poll_cycle += 1
    except Exception as e:
        logger.error(f"Error do_poll_item {poll_pointer}, {item}: {e}")
        raise
"""
            out = patch_switch(src)
            self.assertIn("startup_once_complete", out)
            self.assertIn("force_poll_all_regular", out)
            self.assertIn("item_phases", out)
            self.assertNotIn("force poll including onceonlies", out)
            self.assertIn("startup-only ONCE poll group completed", out)
            self.assertIn("community-scripts: fail-soft poll value conversion", out)
            self.assertIn("except (UnicodeError, ValueError, IndexError, OverflowError)", out)
            self.assertIn("return 0xFD", out)

        def test_switch_failsoft_upgrade(self):
            src = """community-scripts: phased poll scheduler runtime
def do_poll_item():
    try:
        return 1
    except Exception as e:
        logger.error(f"Error do_poll_item {poll_pointer}, {item}: {e}")
        raise
"""
            out = patch_switch(src)
            self.assertIn("community-scripts: fail-soft poll value conversion", out)
            self.assertIn("return 0xFD", out)

        def test_idempotent_markers(self):
            p = "community-scripts: phased group poll scheduler\n"
            self.assertEqual(patch_c_polllist(p), p)
            s = (
                "community-scripts: phased poll scheduler runtime\n"
                "community-scripts: fail-soft poll value conversion\n"
            )
            self.assertEqual(patch_switch(s), s)

        def test_git_blob(self):
            self.assertEqual(
                git_blob_sha(b"test\n"),
                "9daeafb9864cf43055ae93beb0afd6c7d144bfa4",
            )

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("PHASED_POLL_SCHEDULER_TESTS=5/5")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    states = {rel: state_for(ROOT / rel, rel) for rel in PATCHERS}
    for rel, state in states.items():
        print(f"{rel}: {state}")

    if not args.apply:
        print("RESULT=CHECK_ONLY")
        return 0

    if os.geteuid() != 0:
        print("ERROR: --apply requires root", file=sys.stderr)
        return 1

    try:
        apply(ROOT)
        return 0
    except Exception as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
