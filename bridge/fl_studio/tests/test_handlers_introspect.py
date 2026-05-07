# bridge/fl_studio/tests/test_handlers_introspect.py
"""Unit tests for handlers_introspect.py."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import install_fl_mocks, uninstall_fl_mocks


class CapabilityProbeTests(unittest.TestCase):
    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_introspect" in sys.modules:
            importlib.reload(sys.modules["handlers_introspect"])
        import handlers_introspect
        # Reset the module-level cache between tests
        handlers_introspect._CAPS = None
        self.module = handlers_introspect

    def tearDown(self):
        self.module._CAPS = None
        uninstall_fl_mocks()

    def test_probe_reports_full_capabilities_on_fl_2024(self):
        # All FL 2024+ features present by default in the mock
        caps = self.module._probe_capabilities()
        self.assertEqual(caps["api_version"], 36)
        self.assertEqual(caps["fl_version"], "21.2.3.4321")
        self.assertTrue(caps["has_send_levels"])
        self.assertTrue(caps["has_eq_getters"])
        self.assertTrue(caps["has_save_undo"])
        self.assertTrue(caps["has_pattern_length"])
        self.assertTrue(caps["has_slot_color"])
        self.assertTrue(caps["_has_floor_core"])

    def test_probe_caches_after_first_call(self):
        first = self.module._probe_capabilities()
        # Mutate the cache to prove the second call returns the same object.
        first["_test_marker"] = "cached"
        second = self.module._probe_capabilities()
        self.assertEqual(second.get("_test_marker"), "cached")

    def test_probe_with_missing_fl_2024_features(self):
        # Strip FL 2024 functions
        del self.mocks["mixer"].getRouteToLevel
        del self.mocks["mixer"].getEqGain
        del self.mocks["mixer"].getSlotColor
        caps = self.module._probe_capabilities()
        self.assertFalse(caps["has_send_levels"])
        self.assertFalse(caps["has_eq_getters"])
        self.assertFalse(caps["has_slot_color"])
        # Floor core untouched
        self.assertTrue(caps["_has_floor_core"])

    def test_probe_with_missing_floor_core(self):
        del self.mocks["channels"].getChannelType
        caps = self.module._probe_capabilities()
        self.assertFalse(caps["_has_floor_core"])

    def test_probe_falls_back_when_imports_raise(self):
        # Simulate cold-start: remove all FL modules so `import mixer` raises
        uninstall_fl_mocks()
        # Don't install anything back — modules are simply missing
        # Reload the introspect module to reset state
        import importlib
        if "handlers_introspect" in sys.modules:
            importlib.reload(sys.modules["handlers_introspect"])
        import handlers_introspect
        handlers_introspect._CAPS = None
        caps = handlers_introspect._probe_capabilities()
        self.assertEqual(caps["api_version"], 0)
        self.assertEqual(caps["fl_version"], "unknown")
        self.assertFalse(caps["has_send_levels"])
        self.assertFalse(caps["_has_floor_core"])

    def test_probe_re_probes_after_failed_initial(self):
        # First call: simulate failure (no FL modules)
        uninstall_fl_mocks()
        import importlib
        if "handlers_introspect" in sys.modules:
            importlib.reload(sys.modules["handlers_introspect"])
        import handlers_introspect
        handlers_introspect._CAPS = None
        first = handlers_introspect._probe_capabilities()
        self.assertEqual(first["api_version"], 0)
        # Now install mocks (simulating FL finishing boot) and call again
        self.mocks = install_fl_mocks()
        second = handlers_introspect._probe_capabilities()
        self.assertEqual(second["api_version"], 36)
        self.assertTrue(second["_has_floor_core"])


if __name__ == "__main__":
    unittest.main()
