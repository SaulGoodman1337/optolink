#!/usr/bin/env python3
"""Apply the narrow read-only VS1 GFA_READ integration patch to optolink-splitter.

Targets the pinned upstream runtime used by the WB2A/VDensHO1 installation.
The patch adds only:
- optolinkvs1.read_gfa_ext() using VS1 function 0x6B;
- vs12_adapter.read_gfa_ext();
- requests_util support for poll scale/type markers "gfa:<format>";
- explicit read-only command: gfaread;<addr>;1;[format];[signed].

No GFA_WRITE, PROCESS_WRITE, coding write, actuator command, gas-valve command,
or other new write path is added.

Default: --check. Use --apply only when explicitly staging the integration.
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

VERSION = "1.0.3"
ROOT = Path("/opt/optolink")
UPSTREAM_REF = "c1ee204a1421447721603c5f21c6da7337fdac97"

BASE_BLOBS = {
    "optolinkvs1.py": "cff6b4d8d52ca4ee1f79c310dd9377dba1a18270",
    "vs12_adapter.py": "dfcd97cbe598bb71aafd5c1735e1fb4018b8be68",
    "requests_util.py": "0e2b94547518bde504632579d5d7c4da45e56db7",
}

MARKERS = {
    "optolinkvs1.py": "community-scripts: read-only GFA_READ 0x6B",
    "vs12_adapter.py": "def read_gfa_ext(addr:int, rdlen:int, ser:serial.Serial)",
    "requests_util.py": 'poll-item scale/type beginning with "gfa:"',
}


class PatchError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def read_preserve(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def write_preserve(path: Path, text: str) -> None:
    st = path.stat()
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".gfa.", dir=str(path.parent))
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


def patch_optolinkvs1(text: str) -> str:
    if MARKERS["optolinkvs1.py"] in text:
        return text
    nl = newline_of(text)
    marker = f"def write_datapoint(addr:int, data:bytes, ser:serial.Serial) -> bool:{nl}"
    if marker not in text:
        raise PatchError("optolinkvs1.py insertion marker not found")
    block = nl.join([
        "# community-scripts: read-only GFA_READ 0x6B",
        "def read_gfa_ext(addr:int, rdlen:int, ser:serial.Serial) -> tuple[int, int, bytearray]:",
        "    # Locally validated GFA targets P80/P06/P09/P87 are one byte.",
        "    # Refuse other lengths until they have their own hardware evidence.",
        "    if rdlen != 1:",
        "        return 0xFD, addr, bytearray()",
        "",
        "    outbuff = bytearray([0x6B, (addr >> 8) & 0xFF, addr & 0xFF, rdlen])",
        "",
        "    if sync_elapsed():",
        "        outbuff = bytearray([0x01]) + outbuff",
        "        if not re_init(ser):",
        "            return 0xFF, addr, bytearray()",
        "",
        "    ser.reset_input_buffer()",
        "    ser.write(outbuff)",
        "    retcode, retaddr, data = receive_resp_telegr(rdlen, addr, ser)",
        "",
        "    # Earlier long-run GFA captures showed isolated 0xFF acquisitions",
        "    # that must not become physical values (for example P06 => 7650 rpm).",
        "    # Polling publishes only retcode 0x01, so quarantine FF as a failed",
        "    # acquisition with no data payload.",
        "    if retcode == 0x01 and len(data) == 1 and data[0] == 0xFF:",
        "        logger.warning(f\"GFA_READ 0x{addr:04X} returned FF; quarantined\")",
        "        return 0xFF, retaddr, bytearray()",
        "",
        "    return retcode, retaddr, data",
        "",
        "",
    ])
    return text.replace(marker, block + marker, 1)


def patch_adapter(text: str) -> str:
    if MARKERS["vs12_adapter.py"] in text:
        return text
    nl = newline_of(text)
    marker = f"def write_datapoint_ext(addr:int, data:bytes, ser:serial.Serial) -> tuple[int, int, bytearray]:{nl}"
    if marker not in text:
        raise PatchError("vs12_adapter.py insertion marker not found")
    block = nl.join([
        "def read_gfa_ext(addr:int, rdlen:int, ser:serial.Serial) -> tuple[int, int, bytearray]:",
        "    # GFA_READ 0x6B is VS1/KW-only. Never switch protocols implicitly.",
        "    if VS2:",
        "        return 0xAF, addr, bytearray()",
        "    return optolinkvs1.read_gfa_ext(addr, rdlen, ser)",
        "",
        "",
    ])
    return text.replace(marker, block + marker, 1)


def patch_requests(text: str) -> str:
    nl = newline_of(text)
    durable_guard_marker = (
        "Transient P80 transport failures keep the last validated identity."
    )

    # Upgrade an already patched v1.0.2 requests_util.py in place. Earlier
    # versions cleared the P80 identity guard on any transient read failure,
    # which could suppress P06/P09/P87 until the next NORMAL P80 poll.
    if MARKERS["requests_util.py"] in text:
        if durable_guard_marker in text:
            return text

        old_guard = nl.join([
            "                if addr == 0x4050:",
            "                    _community_gfa_p80_ok = (",
            "                        retcode == 1 and len(data) == 1 and data[0] == 0x20",
            "                    )",
            "                    if retcode == 1 and not _community_gfa_p80_ok:",
            "                        logger.warning(",
            '                            "GFA P80 identity mismatch; suppressing productive GFA reads"',
            "                        )",
        ])
        new_guard = nl.join([
            "                if addr == 0x4050:",
            "                    # Transient P80 transport failures keep the last validated identity.",
            "                    # A successful non-0x20 P80 read still revokes the guard immediately.",
            "                    if retcode == 1:",
            "                        _community_gfa_p80_ok = (",
            "                            len(data) == 1 and data[0] == 0x20",
            "                        )",
            "                        if not _community_gfa_p80_ok:",
            "                            logger.warning(",
            '                                "GFA P80 identity mismatch; suppressing productive GFA reads"',
            "                            )",
        ])
        if old_guard not in text:
            raise PatchError(
                "requests_util.py is patched but does not match the supported "
                "v1.0.2 guard layout"
            )
        return text.replace(old_guard, new_guard, 1)

    start = text.find(
        '        elif((cmnd in ["read", "r"]) or ispollitem):  # "read;0x0804;1;0.1;False"'
    )
    end = text.find(f"{nl}        elif(cmnd in [\"write\", \"w\"]):", start)
    if start < 0 or end < 0:
        raise PatchError("requests_util.py read block markers not found")

    block = nl.join([
        '        elif((cmnd in ["read", "r"]) or ispollitem):  # regular read or poll item',
        "            # read +++++++++++++++++++",
        "            addr = utils.get_int(parts[1])",
        "",
        '            # community-scripts: a poll-item scale/type beginning with "gfa:"',
        "            # selects read-only VS1 GFA_READ 0x6B instead of Virtual_READ 0xF7.",
        '            # Example: ("FAST", "gfa_p06", 0x4006, 1, "gfa:30", False)',
        "            gfa_format = None",
        "            if ispollitem and numelms > 3 and isinstance(parts[3], str):",
        "                marker = str(parts[3])",
        '                if marker.lower().startswith("gfa:"):',
        '                    gfa_format = marker[4:] or "raw"',
        "",
        "            if gfa_format is not None:",
        "                # P80 (0x4050) is the local GFA branch identity.",
        "                global _community_gfa_p80_ok",
        "                try:",
        "                    gfa_p80_ok = _community_gfa_p80_ok",
        "                except NameError:",
        "                    _community_gfa_p80_ok = False",
        "                    gfa_p80_ok = False",
        "                if addr != 0x4050 and not gfa_p80_ok:",
        "                    retcode, data = 0xAF, bytearray()",
        "                else:",
        "                    retcode, addr, data = vs12_adapter.read_gfa_ext(addr, int(parts[2]), serViDev)",
        "                if addr == 0x4050:",
        "                    # Transient P80 transport failures keep the last validated identity.",
        "                    # A successful non-0x20 P80 read still revokes the guard immediately.",
        "                    if retcode == 1:",
        "                        _community_gfa_p80_ok = (",
        "                            len(data) == 1 and data[0] == 0x20",
        "                        )",
        "                        if not _community_gfa_p80_ok:",
        "                            logger.warning(",
        '                                "GFA P80 identity mismatch; suppressing productive GFA reads"',
        "                            )",
        "                if retcode == 1:",
        "                    signd = utils.get_bool(parts[4]) if numelms > 4 else False",
        "                    val = get_value(data, gfa_format, signd)",
        "                elif data:",
        "                    val = utils.arr2hexstr(data)",
        "                else:",
        '                    val = "?"',
        "            elif(addr in settings.w1sensors):",
        "                # 1wire sensor",
        "                retcode, val = onewire_util.read_w1sensor(addr)",
        "                val = w1values[addr].checked(val)",
        "            else:",
        "                # Optolink Virtual_READ item",
        "                retcode, addr, data = vs12_adapter.read_datapoint_ext(addr, int(parts[2]), serViDev)",
        "                if(retcode==1):",
        "                    if(numelms > 3):",
        "                        if(str(parts[3]).startswith('b:')):",
        "                            val = perform_bytebit_filter_and_evaluate(data, parts)",
        "                        else:",
        "                            signd = False",
        "                            if(numelms > 4):",
        "                                signd = utils.get_bool(parts[4])",
        "                            val = get_value(data, parts[3], signd)",
        "                    else:",
        "                        val = utils.arr2hexstr(data)",
        "                elif(data):",
        "                    val = utils.arr2hexstr(data)",
        "                else:",
        '                    val = "?"',
        "            retstr = get_retstr(retcode, addr, val)",
        "",
        '        elif(cmnd in ["gfaread", "gr"]):',
        "            # community-scripts: explicit read-only VS1 GFA_READ 0x6B.",
        "            # Syntax: gfaread;<addr>;1;[format];[signed]",
        "            addr = utils.get_int(parts[1])",
        "            rlen = int(parts[2])",
        '            frmat = parts[3] if numelms > 3 and parts[3] else "raw"',
        "            signd = utils.get_bool(parts[4]) if numelms > 4 else False",
        "            retcode, addr, data = vs12_adapter.read_gfa_ext(addr, rlen, serViDev)",
        "            if retcode == 1:",
        "                val = get_value(data, frmat, signd)",
        "            elif data:",
        "                val = utils.arr2hexstr(data)",
        "            else:",
        '                val = "?"',
        "            retstr = get_retstr(retcode, addr, val)",
        "",
    ])
    return text[:start] + block + text[end:]


PATCHERS = {
    "optolinkvs1.py": patch_optolinkvs1,
    "vs12_adapter.py": patch_adapter,
    "requests_util.py": patch_requests,
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


def check_root() -> dict[str, str]:
    return {rel: state_for(ROOT / rel, rel) for rel in PATCHERS}


def apply(root: Path) -> Path:
    global ROOT
    old_root = ROOT
    ROOT = root
    try:
        states = check_root()
        bad = {k: v for k, v in states.items() if v not in ("base", "patched")}
        if bad:
            raise PatchError("refusing unexpected runtime files: " + repr(bad))

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = Path("/root") / f"optolink-vs1-gfa-readonly-backup-{stamp}-{os.getpid()}"
        if root != Path("/opt/optolink"):
            backup = root / ".gfa-test-backup"
        backup.mkdir(mode=0o700, parents=True, exist_ok=False)

        changed = []
        for rel, patcher in PATCHERS.items():
            path = root / rel
            shutil.copy2(path, backup / rel)
            original = read_preserve(path)
            patched = patcher(original)
            if patched != original:
                write_preserve(path, patched)
                changed.append(rel)

        for rel in PATCHERS:
            py_compile.compile(str(root / rel), doraise=True)

        for rel in PATCHERS:
            if MARKERS[rel] not in read_preserve(root / rel):
                raise PatchError(f"post-patch marker missing in {rel}")

        print("PATCHED_FILES=" + ",".join(changed))
        print("BACKUP=" + str(backup))
        for rel in PATCHERS:
            print(f"{rel} blob={git_blob_sha((root / rel).read_bytes())}")
        print("RESULT=PASS")
        return backup
    except Exception:
        raise
    finally:
        ROOT = old_root


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_git_blob(self):
            self.assertEqual(
                git_blob_sha(b"test\n"),
                "9daeafb9864cf43055ae93beb0afd6c7d144bfa4",
            )

        def test_optolinkvs1_patch(self):
            src = "x\r\ndef write_datapoint(addr:int, data:bytes, ser:serial.Serial) -> bool:\r\n    pass\r\n"
            out = patch_optolinkvs1(src)
            self.assertIn("0x6B", out)
            self.assertIn("\r\n", out)
            self.assertEqual(patch_optolinkvs1(out), out)

        def test_adapter_patch(self):
            src = "x\ndef write_datapoint_ext(addr:int, data:bytes, ser:serial.Serial) -> tuple[int, int, bytearray]:\n    pass\n"
            out = patch_adapter(src)
            self.assertIn("read_gfa_ext", out)
            self.assertEqual(patch_adapter(out), out)

        def test_requests_patch(self):
            src = (
                'x\n'
                '        elif((cmnd in ["read", "r"]) or ispollitem):  # "read;0x0804;1;0.1;False"\n'
                '            OLD\n'
                '        elif(cmnd in ["write", "w"]):\n'
                '            WRITE\n'
            )
            out = patch_requests(src)
            self.assertIn('gfa_format', out)
            self.assertIn('gfaread', out)
            self.assertIn('elif(cmnd in ["write", "w"]):', out)
            self.assertEqual(patch_requests(out), out)

        def test_p80_identity_guard_is_present(self):
            src = (
                '        elif((cmnd in ["read", "r"]) or ispollitem):  # "read;0x0804;1;0.1;False"\n'
                '            OLD\n'
                '        elif(cmnd in ["write", "w"]):\n'
                '            WRITE\n'
            )
            out = patch_requests(src)
            self.assertIn('_community_gfa_p80_ok', out)
            self.assertIn('addr != 0x4050 and not gfa_p80_ok', out)
            self.assertIn('data[0] == 0x20', out)

        def test_p80_transient_failure_keeps_identity(self):
            src = (
                '        elif((cmnd in ["read", "r"]) or ispollitem):  # "read;0x0804;1;0.1;False"\n'
                '            OLD\n'
                '        elif(cmnd in ["write", "w"]):\n'
                '            WRITE\n'
            )
            out = patch_requests(src)
            self.assertIn(
                "Transient P80 transport failures keep the last validated identity.",
                out,
            )
            self.assertIn("if retcode == 1:", out)
            self.assertNotIn(
                "retcode == 1 and len(data) == 1 and data[0] == 0x20",
                out,
            )

        def test_p80_v102_upgrade(self):
            src = (
                'community-scripts: a poll-item scale/type beginning with "gfa:"\n'
                '                if addr == 0x4050:\n'
                '                    _community_gfa_p80_ok = (\n'
                '                        retcode == 1 and len(data) == 1 and data[0] == 0x20\n'
                '                    )\n'
                '                    if retcode == 1 and not _community_gfa_p80_ok:\n'
                '                        logger.warning(\n'
                '                            "GFA P80 identity mismatch; suppressing productive GFA reads"\n'
                '                        )\n'
            )
            out = patch_requests(src)
            self.assertIn(
                "Transient P80 transport failures keep the last validated identity.",
                out,
            )
            self.assertNotIn(
                "retcode == 1 and len(data) == 1 and data[0] == 0x20",
                out,
            )
            self.assertEqual(patch_requests(out), out)

        def test_ff_quarantine_is_present(self):
            src = "def write_datapoint(addr:int, data:bytes, ser:serial.Serial) -> bool:\n    pass\n"
            out = patch_optolinkvs1(src)
            self.assertIn("data[0] == 0xFF", out)
            self.assertIn("returned FF; quarantined", out)
            self.assertIn("return 0xFF, retaddr, bytearray()", out)

        def test_patch_contains_no_new_write_function(self):
            sample = (
                '        elif((cmnd in ["read", "r"]) or ispollitem):  # "read;0x0804;1;0.1;False"\n'
                '            OLD\n'
                '        elif(cmnd in ["write", "w"]):\n'
                '            WRITE\n'
            )
            out = patch_requests(sample)
            inserted = out.split('        elif(cmnd in ["write", "w"]):', 1)[0]
            self.assertNotIn("GFA_WRITE", inserted)
            self.assertNotIn("0x68", inserted)
            self.assertIn("0x6B", patch_optolinkvs1(
                "def write_datapoint(addr:int, data:bytes, ser:serial.Serial) -> bool:\n    pass\n"
            ))

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("VS1_GFA_READONLY_PATCH_TESTS=9/9")
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

    states = check_root()
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
