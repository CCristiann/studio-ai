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
        # NOTE: this test relies on the cache returning the SAME dict object
        # (not a copy). If _probe_capabilities is ever changed to return
        # `dict(_CAPS)` or similar, this test stops verifying caching and
        # silently passes — replace it with an identity check (`is`) or
        # spy on the import path.
        first = self.module._probe_capabilities()
        first["_test_marker"] = "cached"
        second = self.module._probe_capabilities()
        self.assertEqual(second.get("_test_marker"), "cached")
        # Belt-and-suspenders: also assert identity directly.
        self.assertIs(first, second)

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


class ChannelPluginTests(unittest.TestCase):
    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_introspect" in sys.modules:
            importlib.reload(sys.modules["handlers_introspect"])
        import handlers_introspect
        handlers_introspect._CAPS = None
        self.module = handlers_introspect

    def tearDown(self):
        self.module._CAPS = None
        uninstall_fl_mocks()

    def test_channel_plugin_vst(self):
        self.mocks["channels"].types = {3: 2}
        self.mocks["plugins"].names = {(3, -1): "Sytrus"}
        self.mocks["plugins"].valid = {(3, -1): True}
        result = self.module._channel_plugin(3)
        self.assertEqual(result, {"name": "Sytrus", "type": 2, "type_label": "vst"})

    def test_channel_plugin_sampler(self):
        self.mocks["channels"].types = {0: 0}
        self.mocks["plugins"].names = {(0, -1): ""}
        result = self.module._channel_plugin(0)
        self.assertEqual(result, {"name": "", "type": 0, "type_label": "sampler"})

    def test_channel_plugin_unknown_type_code(self):
        self.mocks["channels"].types = {1: 99}
        self.mocks["plugins"].names = {(1, -1): "Mystery"}
        result = self.module._channel_plugin(1)
        self.assertEqual(result, {"name": "Mystery", "type": 99, "type_label": "unknown"})

    def test_channel_plugin_returns_none_when_get_channel_type_raises(self):
        def boom(_i):
            raise RuntimeError("boom")
        self.mocks["channels"].getChannelType = boom
        result = self.module._channel_plugin(0)
        self.assertIsNone(result)

    def test_channel_plugin_empty_name_when_get_plugin_name_raises(self):
        self.mocks["channels"].types = {0: 2}
        def boom(*a, **k):
            raise RuntimeError("boom")
        self.mocks["plugins"].getPluginName = boom
        result = self.module._channel_plugin(0)
        self.assertEqual(result, {"name": "", "type": 2, "type_label": "vst"})


class MixerRoutesTests(unittest.TestCase):
    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_introspect" in sys.modules:
            importlib.reload(sys.modules["handlers_introspect"])
        import handlers_introspect
        handlers_introspect._CAPS = None
        self.module = handlers_introspect

    def tearDown(self):
        self.module._CAPS = None
        uninstall_fl_mocks()

    def test_mixer_routes_includes_active_sends_with_levels(self):
        # Track 5 sends to tracks 7 and 12
        self.mocks["mixer"].routes = {(5, 7): True, (5, 12): True}
        self.mocks["mixer"].route_levels = {(5, 7): 0.5, (5, 12): 0.9}
        result = self.module._mixer_routes(5)
        self.assertEqual(len(result), 2)
        self.assertIn({"to_index": 7, "level": 0.5}, result)
        self.assertIn({"to_index": 12, "level": 0.9}, result)

    def test_mixer_routes_skips_self_route(self):
        self.mocks["mixer"].routes = {(5, 5): True, (5, 7): True}
        result = self.module._mixer_routes(5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["to_index"], 7)

    def test_mixer_routes_empty_when_no_active_sends(self):
        result = self.module._mixer_routes(3)
        self.assertEqual(result, [])

    def test_mixer_routes_omits_level_when_capability_absent(self):
        del self.mocks["mixer"].getRouteToLevel
        self.mocks["mixer"].routes = {(5, 7): True}
        result = self.module._mixer_routes(5)
        self.assertEqual(result, [{"to_index": 7}])

    def test_mixer_routes_handles_per_call_exception_gracefully(self):
        def flaky(src, dst):
            if dst == 9:
                raise RuntimeError("bad pair")
            return src == 5 and dst in (7, 12)
        self.mocks["mixer"].getRouteSendActive = flaky
        result = self.module._mixer_routes(5)
        targets = sorted(r["to_index"] for r in result)
        self.assertEqual(targets, [7, 12])

    def test_mixer_routes_appends_entry_without_level_when_get_route_to_level_raises(self):
        # When getRouteSendActive returns true but getRouteToLevel raises,
        # the route is still recorded — without the `level` key, not dropped.
        self.mocks["mixer"].routes = {(5, 7): True}
        def boom(src, dst):
            raise RuntimeError("level read failed")
        self.mocks["mixer"].getRouteToLevel = boom
        result = self.module._mixer_routes(5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], {"to_index": 7})  # no `level` key


if __name__ == "__main__":
    unittest.main()
