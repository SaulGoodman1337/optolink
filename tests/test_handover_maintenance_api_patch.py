"""Verify patched Maintenance API imports staged fenced core, not /opt module."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.maintenance_api_patch import (
    patch_maintenance_api, MaintenanceApiPatchRejected)


MOCK_API = (
    "import sys\n"
    "APP_DIR='/opt/optolink'\n"
    "if APP_DIR not in sys.path:\n"
    "    sys.path.insert(0, APP_DIR)\n"
    "from optolink_maintenance_core import (get_status,)\n"
)


class MaintenanceModuleRoutingTests(unittest.TestCase):
    def test_shadow_precedence_loads_exact_staged_core(self):
        with tempfile.TemporaryDirectory() as root:
            top=Path(root)
            bin_dir=top/"bin"
            src_dir=top/"src"
            bin_dir.mkdir()
            src_dir.mkdir()
            (top/"stage-manifest.json").write_text("{}")
            core=src_dir/"optolink_maintenance_core.py"
            core.write_text("def get_status():\n    return 42\n")
            script=bin_dir/"optolink-maintenance-api"
            script.write_text(patch_maintenance_api(MOCK_API))
            before_path=sys.path[:]
            old=sys.modules.pop("optolink_maintenance_core",None)
            try:
                scope={"__file__":str(script),"__name__":"fake_running_api"}
                exec(compile(script.read_text(),str(script),"exec"),scope)
                self.assertEqual(scope["get_status"](),42)
                self.assertEqual(Path(sys.modules["optolink_maintenance_core"].__file__),core)
            finally:
                sys.path[:]=before_path
                sys.modules.pop("optolink_maintenance_core",None)
                if old is not None:
                    sys.modules["optolink_maintenance_core"]=old

    def test_invalid_source_or_double_instrumentation_refused(self):
        patched=patch_maintenance_api(MOCK_API)
        self.assertIn("# HYBRID_MAINTENANCE_API_SHADOW_V1",patched)
        with self.assertRaises(MaintenanceApiPatchRejected):
            patch_maintenance_api(patched)
        for bad in (MOCK_API.replace("sys.path.insert(0, APP_DIR)","pass"),
                    MOCK_API.replace("from optolink_maintenance_core import", "from not_the_core import")):
            with self.subTest(code=bad),self.assertRaises(MaintenanceApiPatchRejected):
                patch_maintenance_api(bad)

    def test_missing_core_or_stage_manifest_refuses_import(self):
        with tempfile.TemporaryDirectory() as root:
            top=Path(root)
            (top/"bin").mkdir()
            (top/"src").mkdir()
            script=top/"bin"/"optolink-maintenance-api"
            script.write_text(patch_maintenance_api(MOCK_API))
            with self.assertRaisesRegex(RuntimeError,"lacks an audited core"):
                exec(script.read_text(),{"__file__":str(script),"__name__":"dummy"})


if __name__=="__main__":
    unittest.main()
