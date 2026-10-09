"""Deterministic full-RAM read-only, wire, classification, and archive tests."""
import importlib.util
import io
import json
from pathlib import Path
import signal
import tarfile
import tempfile
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parents[1] / "tools" / "wb2a-p300-fullram-logger.py"
spec = importlib.util.spec_from_file_location("fullram", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Port:
    def __init__(self):
        self.tx = []
    def write(self, data):
        self.tx.append(data)
        return len(data)

class Peer:
    def __init__(self, data, *, on_read=None):
        self.port = Port()
        self.t = 0.0
        self.trace = []
        self.on_read = on_read
        fc, addr, length, payload = data
        body = bytes((1, fc, addr >> 8, addr & 255, length)) + payload
        n = 5 + len(payload)
        self.rx = [b"\x06", b"\x41", bytes((n,)), body + bytes(((n + sum(body)) & 255,))]
    def clock(self):
        self.t += .01
        return self.t
    def gap(self): pass
    def quiet(self): pass
    def exact(self, n, deadline):
        if self.on_read:
            self.on_read()
        value = self.rx.pop(0)
        assert len(value) == n
        return value
    def record(self, direction, data):
        self.trace.append((direction, data.hex()))

class FullRam(unittest.TestCase):
    def setUp(self):
        m.DEEP.BASE = None

    def test_exact_geometry(self):
        a = m.addresses()
        self.assertEqual(len(a), 640)
        self.assertEqual(len(set(a)), 640)
        self.assertEqual((a[0], a[-1]), (0x0400, 0x53e0))
        self.assertEqual(m.addresses(True), tuple(reversed(a)))
        self.assertEqual(len(a) * 32, 20480)

    def test_readonly_whitelist(self):
        self.assertEqual(m.request_frame(3, 0x0400, 32).hex(), "410500030400202c")
        self.assertEqual(m.request_frame(3, 0x53e0, 32).hex(), "4105000353e0205b")
        self.assertEqual(m.request_frame(*m.STATUS_SPEC).hex(), "4105000155d30b39")
        for fc, addr, count in [(4, 0x0400, 32), (2, 0x0400, 32),
                                (0xC9, 0x4006, 1), (3, 0x03e0, 32),
                                (3, 0x5400, 32), (3, 0x0401, 32),
                                (3, 0x0400, 31), (3, 0x03ae, 32),
                                (3, 0x0020, 16)]:
            with self.subTest(fc=fc, address=hex(addr)):
                with self.assertRaisesRegex(ValueError, "UNREVIEWED"):
                    m.request_frame(fc, addr, count)

    def test_all_frames_checksum_valid(self):
        for addr in m.addresses():
            f = m.request_frame(3, addr, 32)
            self.assertEqual(len(f), 8)
            self.assertEqual(f[-1], sum(f[1:-1]) & 255)

    def test_wire_exact_frame_and_signal_deferred(self):
        latch = m.DEEP.DeferredStop()
        data = bytes(range(32))
        peer = Peer((3, 0x0400, 32, data), on_read=lambda: latch.on_signal(signal.SIGTERM, None))
        wire = m.FullRamWire(peer)
        wire.set_phase("p300")
        with patch.object(m.DEEP, "load_local_base", return_value=type("B", (), {"h": type("H", (), {})()})()):
            got = wire.packet((3, 0x0400, 32))
        self.assertEqual(got["data"], data)
        self.assertTrue(got["checksum_valid"])
        self.assertEqual(peer.port.tx, [m.request_frame(3, 0x0400, 32), b"\x06"])
        with self.assertRaisesRegex(RuntimeError, "OPERATOR_STOP_SIGNAL"):
            latch.check()

    def test_payload_corruption_fails_closed(self):
        peer = Peer((3, 0x0400, 32, bytes(32)))
        bad = bytearray(peer.rx[-1])
        bad[-1] ^= 1
        peer.rx[-1] = bytes(bad)
        wire = m.FullRamWire(peer)
        wire.set_phase("p300")
        with patch.object(m.DEEP, "load_local_base", return_value=type("B", (), {"h": type("H", (), {})()})()):
            with self.assertRaisesRegex(m.PacketError, "CHECKSUM"):
                wire.packet((3, 0x0400, 32))
        self.assertEqual(len(peer.port.tx), 1)

    def test_quality_is_conservative(self):
        def ref(raw):
            return {"stable": True, "identity_verified": True, "p06_raw_unique": [raw]}
        self.assertEqual(m.classify(ref("00"), ref("00"), []), "STABLE_BRACKET_OFF")
        self.assertEqual(m.classify(ref("53"), ref("53"), []), "STABLE_BRACKET_RUNNING")
        self.assertEqual(m.classify(ref("53"), ref("54"), []), "TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.classify(ref("53"), ref("53"), [{"flame": True}, {"flame": False}]), "TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.classify({**ref("53"), "stable": False}, ref("53"), []), "TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.classify(None, ref("53"), []), "TRANSITION_OR_UNKNOWN")

    def test_binary_forward_reverse_and_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            original = bytes((i * 17 + 3) & 255 for i in range(20480))
            for descending in (False, True):
                payload = b"".join(original[i:i+32] for i in range(0, 20480, 32))
                if descending:
                    payload = b"".join(reversed([payload[i:i+32] for i in range(0, 20480, 32)]))
                part, done = folder / "dump.partial.bin", folder / "dump.bin"
                part.write_bytes(payload)
                dig = m.restore_canonical(part, done, descending)
                self.assertEqual(done.read_bytes(), original)
                self.assertEqual(dig, m.sha256(done))
                done.unlink()

    def test_short_reverse_fails_and_keeps_partial(self):
        with tempfile.TemporaryDirectory() as td:
            part, out = Path(td)/"a.partial.bin", Path(td)/"a.bin"
            part.write_bytes(bytes(20479))
            with self.assertRaisesRegex(RuntimeError, "SHORT_READ"):
                m.restore_canonical(part, out, True)
            self.assertTrue(part.exists())

    def test_disk_and_file_limit(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(m.shutil, "disk_usage", return_value=type("U", (), {"free": 1})()):
                with self.assertRaisesRegex(RuntimeError, "DISK"):
                    m.storage_guard(Path(td))
            (Path(td)/"oversize").write_bytes(b"abcd")
            with patch.object(m, "MAX_SESSION_BYTES", 3):
                with self.assertRaisesRegex(RuntimeError, "SESSION_SIZE"):
                    m.storage_guard(Path(td))

    def test_archive_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "results"; root.mkdir()
            bundles = Path(td) / "bundle"; bundles.mkdir()
            session = root / "run-test"; session.mkdir()
            (session / "state.json").write_text('{"read_only":true}')
            (session / "snapshots").mkdir()
            (session / "snapshots" / "s00001.partial.bin").write_bytes(b"\x01\x02")
            with patch.object(m, "ROOT", root), patch.object(m, "BUNDLES", bundles):
                with patch.object(m.os, "geteuid", return_value=0):
                    # Tests may run as non-root; archive checks ownership.
                    if (session / "state.json").stat().st_uid != 0:
                        self.skipTest("Archive root-only validation")
                    result = m.archive(session)
            with tarfile.open(result, "r:gz") as tar:
                manifest = json.load(tar.extractfile("p300-fullram/bundle-manifest.json"))
                for filename, row in manifest["files"].items():
                    payload = tar.extractfile("p300-fullram/" + filename).read()
                    self.assertEqual(len(payload), row["size"])
                    import hashlib
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), row["sha256"])
                self.assertFalse(manifest["rpm_alias_verified"])

    def test_progress_counts_logged_switches_not_unrelated_frames(self):
        from collections import Counter
        from types import SimpleNamespace
        import time
        with tempfile.TemporaryDirectory() as td:
            session = Path(td)
            switches = session / "switch.jsonl"
            switches.write_text(''.join(json.dumps({"result": state}) + "\n"
                                        for state in ("OK", "OK", "ERROR")))
            captured = []
            base = SimpleNamespace(h=SimpleNamespace(atomic_json=lambda path, data: captured.append(data)))
            counts = Counter()
            with patch.object(m.DEEP, "load_local_base", return_value=base):
                m.progress(session, "P300_SCAN", counts, time.monotonic(), 4)
            self.assertEqual(counts["SWITCHES"], 3)
            self.assertEqual(captured[0]["switch_count"], 3)

    def test_stop_guard_and_recovery_dependencies(self):
        self.assertEqual(m.UNIT, "optolink-p300-fullram-logger.service")
        self.assertEqual(m.DEFAULT_HOURS, 4)
        self.assertIn("optolink-p300-deep-logger.service", (m.DEEP.UNIT,))
        self.assertFalse(m.classify(None, None, []) == "STABLE_BRACKET_RUNNING")

if __name__ == "__main__":
    unittest.main()
