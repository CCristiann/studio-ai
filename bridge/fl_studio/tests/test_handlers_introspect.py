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


class SmallHelperTests(unittest.TestCase):
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

    def test_slot_count_matches_valid_slots(self):
        self.mocks["plugins"].valid = {
            (5, 0): True, (5, 1): True, (5, 3): True,  # 3 loaded
        }
        self.assertEqual(self.module._mixer_slot_count(5), 3)

    def test_slot_count_zero_when_no_slots_loaded(self):
        self.assertEqual(self.module._mixer_slot_count(5), 0)

    def test_slot_count_continues_past_per_slot_exception(self):
        def flaky(track, slot, useGlobalIndex=False):
            if slot == 3:
                raise RuntimeError("slot 3 broken")
            return (track, slot) in {(5, 0), (5, 1), (5, 5), (5, 6)}
        self.mocks["plugins"].isValid = flaky
        # Slots 0,1 valid; 3 raises (skipped, not break); 5,6 valid → count = 4
        self.assertEqual(self.module._mixer_slot_count(5), 4)

    def test_selection_returns_all_three_indices(self):
        self.mocks["channels"]._selected_channel = 7
        self.mocks["patterns"]._selected_pattern = 12
        self.mocks["mixer"]._selected_track = 4
        sel = self.module._selection()
        self.assertEqual(sel, {
            "channel_index": 7, "pattern_index": 12, "mixer_track_index": 4,
        })

    def test_selection_partial_when_one_function_raises(self):
        def boom(*a, **k):
            raise RuntimeError("boom")
        self.mocks["mixer"].trackNumber = boom
        self.mocks["channels"]._selected_channel = 1
        self.mocks["patterns"]._selected_pattern = 2
        sel = self.module._selection()
        self.assertEqual(sel["channel_index"], 1)
        self.assertEqual(sel["pattern_index"], 2)
        self.assertIsNone(sel["mixer_track_index"])


class GetProjectStateTests(unittest.TestCase):
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

    def _set_one_channel(self, idx, name, type_code, plugin_name):
        self.mocks["channels"].names = {idx: name}
        self.mocks["channels"].types = {idx: type_code}
        self.mocks["plugins"].names = {(idx, -1): plugin_name}

    def test_returns_floor_unsupported_when_floor_core_missing(self):
        del self.mocks["channels"].getChannelType
        result = self.module._cmd_get_project_state({})
        self.assertEqual(result.get("success"), False)
        self.assertEqual(result.get("error"), "FL_VERSION_UNSUPPORTED")

    def test_includes_top_level_metadata(self):
        result = self.module._cmd_get_project_state({})
        self.assertIn("bpm", result)
        self.assertIn("project_name", result)
        self.assertIn("playing", result)
        self.assertIn("snapshot_at", result)
        self.assertIn("capabilities", result)
        self.assertIn("selection", result)

    def test_channel_includes_plugin_object(self):
        self._set_one_channel(0, "Lead", 2, "Sytrus")
        result = self.module._cmd_get_project_state({})
        self.assertEqual(len(result["channels"]), 1)
        ch = result["channels"][0]
        self.assertEqual(ch["plugin"], {"name": "Sytrus", "type": 2, "type_label": "vst"})

    def test_mixer_track_includes_slot_count_and_routes(self):
        self.mocks["mixer"].names = {7: "DRUMS"}
        self.mocks["plugins"].valid = {(7, 0): True, (7, 1): True}
        self.mocks["mixer"].routes = {(7, 88): True}
        self.mocks["mixer"].route_levels = {(7, 88): 0.7}
        result = self.module._cmd_get_project_state({})
        track = next(t for t in result["mixer_tracks"] if t["index"] == 7)
        self.assertEqual(track["slot_count"], 2)
        self.assertEqual(track["routes_to"], [{"to_index": 88, "level": 0.7}])

    def test_filtering_includes_track_with_only_slots_loaded(self):
        # No name, no color, but ≥1 loaded slot — should be retained
        self.mocks["plugins"].valid = {(15, 0): True}
        result = self.module._cmd_get_project_state({})
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertIn(15, indices)

    def test_filtering_includes_track_with_only_outbound_route(self):
        self.mocks["mixer"].routes = {(20, 88): True}
        result = self.module._cmd_get_project_state({})
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertIn(20, indices)

    def test_pattern_length_included_when_capability_present(self):
        self.mocks["patterns"].names = {1: "Verse"}
        self.mocks["patterns"].lengths = {1: 16}
        result = self.module._cmd_get_project_state({})
        pat = next(p for p in result["patterns"] if p["index"] == 1)
        self.assertEqual(pat["length_beats"], 16)

    def test_pattern_length_omitted_when_capability_absent(self):
        del self.mocks["patterns"].getPatternLength
        self.mocks["patterns"].names = {1: "Verse"}
        result = self.module._cmd_get_project_state({})
        pat = next(p for p in result["patterns"] if p["index"] == 1)
        self.assertNotIn("length_beats", pat)

    def test_routes_to_excludes_level_when_capability_absent(self):
        del self.mocks["mixer"].getRouteToLevel
        self.mocks["mixer"].names = {5: "Bus"}
        self.mocks["mixer"].routes = {(5, 88): True}
        result = self.module._cmd_get_project_state({})
        track = next(t for t in result["mixer_tracks"] if t["index"] == 5)
        self.assertEqual(track["routes_to"], [{"to_index": 88}])

    def test_selection_state_in_response(self):
        self.mocks["channels"]._selected_channel = 3
        self.mocks["patterns"]._selected_pattern = 5
        self.mocks["mixer"]._selected_track = 7
        result = self.module._cmd_get_project_state({})
        self.assertEqual(result["selection"], {
            "channel_index": 3, "pattern_index": 5, "mixer_track_index": 7,
        })


class TruncationTests(unittest.TestCase):
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

    def test_include_routing_false_skips_sweep(self):
        # If include_routing=False, _mixer_routes should never be called.
        # Check by configuring routes that, if the sweep ran, would appear.
        self.mocks["mixer"].names = {5: "Bus"}
        self.mocks["mixer"].routes = {(5, 88): True}
        result = self.module._cmd_get_project_state({"include_routing": False})
        track = next(t for t in result["mixer_tracks"] if t["index"] == 5)
        self.assertEqual(track["routes_to"], [])

    def test_channels_truncated_at_cap(self):
        # 300 channels; cap is 256
        self.mocks["channels"].names = {i: f"Ch{i}" for i in range(300)}
        self.mocks["channels"].types = {i: 2 for i in range(300)}
        result = self.module._cmd_get_project_state({})
        self.assertEqual(len(result["channels"]), 256)
        self.assertIn("channels", result.get("truncated_sections", []))

    def test_patterns_truncated_at_cap(self):
        self.mocks["patterns"].names = {i: f"P{i}" for i in range(1, 300)}
        result = self.module._cmd_get_project_state({})
        self.assertLessEqual(len(result["patterns"]), 256)
        if len(result["patterns"]) == 256:
            self.assertIn("patterns", result.get("truncated_sections", []))

    def test_routing_truncated_when_too_many_retained_inserts(self):
        # Force 110 retained inserts (>100 cap)
        self.mocks["mixer"].names = {i: f"Insert {i}" + "X" for i in range(1, 111)}
        # Configure routing on first track only; verify it appears
        self.mocks["mixer"].routes = {(1, 90): True, (50, 91): True, (105, 92): True}
        result = self.module._cmd_get_project_state({})
        truncated = result.get("truncated_sections", [])
        self.assertIn("routing", truncated)
        self.assertIn("routing_swept_through", result)
        # First 100 tracks (sorted by index ascending) sweep routing
        track_1 = next((t for t in result["mixer_tracks"] if t["index"] == 1), None)
        track_105 = next((t for t in result["mixer_tracks"] if t["index"] == 105), None)
        self.assertIsNotNone(track_1)
        self.assertEqual(track_1["routes_to"], [{"to_index": 90, "level": 0.8}])
        if track_105:
            self.assertEqual(track_105["routes_to"], [])

    def test_no_truncated_sections_when_under_caps(self):
        result = self.module._cmd_get_project_state({})
        # Empty project → no truncation
        self.assertNotIn("truncated_sections", result)


if __name__ == "__main__":
    unittest.main()
