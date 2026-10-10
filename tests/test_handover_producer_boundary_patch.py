"""Offline transaction boundary patcher: no production scripts mutated."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration import producer_boundary_patch as producer
from handover_acceleration import producer_fence


def source_for(kind: str) -> str:
    owner, names = producer.TARGETS[kind]
    if owner is None:
        return (
            "EVENTS = []\n"
            "def _with_session(operation, *, quiet=False):\n"
            "    EVENTS.append('read-before')\n"
            "    answer = operation()\n"
            "    EVENTS.append('readback-complete')\n"
            "    return answer\n"
        )
    methods = "".join(
        f"    def {name}(self):\n"
        f"        EVENTS.append({name!r} + ':write')\n"
        f"        EVENTS.append({name!r} + ':verified_readback')\n"
        for name in names
    )
    return (
        "EVENTS = []\n"
        f"class {owner}:\n"
        f"{methods}"
        "def main():\n"
        "    raise AssertionError('do not call in a unit test')\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )


class ProducerBoundaryPatchTests(unittest.TestCase):
    def test_all_five_producer_sources_get_transaction_scoped_wrappers(self):
        for kind, (owner, names) in producer.TARGETS.items():
            with self.subTest(kind=kind):
                events = []

                @contextmanager
                def fake_writer_transaction(role):
                    self.assertEqual(role, kind)
                    events.append("LEASE_ACQUIRED")
                    try:
                        yield
                    finally:
                        events.append("LEASE_RELEASED")

                with patch.object(producer_fence, "writer_transaction",
                                  fake_writer_transaction):
                    source = producer.patch_producer(source_for(kind), kind)
                    self.assertIn("# HYBRID_PRODUCER_EPOCH_V1", source)
                    namespace = {"__name__": "offline_test"}
                    exec(compile(source, "patched-producer", "exec"), namespace)
                    for name in names:
                        if owner is None:
                            operation = namespace[name]
                            self.assertEqual(
                                operation(lambda: "ok", quiet=True), "ok")
                        else:
                            operation = getattr(namespace[owner](), name)
                            operation()
                        tail = namespace["EVENTS"][-2:]
                        if owner is None:
                            self.assertEqual(tail, ["read-before", "readback-complete"])
                        else:
                            self.assertEqual(tail, [
                                f"{name}:write", f"{name}:verified_readback"])
                        self.assertEqual(events[-2:],
                                         ["LEASE_ACQUIRED", "LEASE_RELEASED"])
                        events.clear()

    def test_failed_writer_still_releases_lease(self):
        src = source_for("schedule").replace(
            "        EVENTS.append('apply' + ':verified_readback')",
            "        raise RuntimeError('rollback incomplete')")
        order = []

        @contextmanager
        def observed_transaction(_kind):
            order.append("lease_open")
            try:
                yield
            finally:
                order.append("lease_close")

        with patch.object(producer_fence, "writer_transaction", observed_transaction):
            ns = {"__name__": "test"}
            exec(producer.patch_producer(src, "schedule"), ns)
            with self.assertRaisesRegex(RuntimeError, 'rollback incomplete'):
                ns["ScheduleManager"]().apply()
        self.assertEqual(order, ["lease_open", "lease_close"])

    def test_schema_drift_and_double_patch_refused(self):
        for kind, (owner, names) in producer.TARGETS.items():
            src = source_for(kind)
            with self.subTest(kind=kind):
                once = producer.patch_producer(src, kind)
                with self.assertRaisesRegex(producer.ProducerPatchRejected,
                                            "already instrumented"):
                    producer.patch_producer(once, kind)
                altered = src.replace(f"def {names[0]}(", "def removed(", 1)
                with self.assertRaisesRegex(producer.ProducerPatchRejected,
                                            "boundary missing"):
                    producer.patch_producer(altered, kind)

    def test_wrong_kind_and_wrong_main_layout_are_refused(self):
        with self.assertRaises(producer.ProducerPatchRejected):
            producer.patch_producer(source_for("party"), "unapproved")
        with self.assertRaises(producer.ProducerPatchRejected):
            producer.patch_producer(source_for("party").replace(
                "if __name__ == '__main__':\n    main()\n", ""), "party")
        with self.assertRaises(producer.ProducerPatchRejected):
            producer.patch_producer(source_for("party").replace(
                "def activate(self):", "async def activate(self):"), "party")

    def test_no_in_place_or_symlink_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder)/"producer.py"
            src.write_text(source_for("schedule"))
            with self.assertRaises(producer.ProducerPatchRejected):
                producer.main(["--kind","schedule","--source",str(src),
                               "--output",str(src)])
            self.assertEqual(src.read_text(), source_for("schedule"))
            link = Path(folder)/"link.py"
            link.symlink_to(src)
            with self.assertRaises(producer.ProducerPatchRejected):
                producer.main(["--kind","schedule","--source",str(link),
                               "--output",str(Path(folder)/"output.py")])
            self.assertFalse((Path(folder)/"output.py").exists())


if __name__ == "__main__":
    unittest.main()
