# bridge/fl_studio/tests/test_handlers_bulk.py
"""Unit tests for handlers_bulk.py — runs outside FL Studio with mocks."""
import os
import sys
import unittest

# Make bridge/fl_studio importable when running from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import install_fl_mocks, uninstall_fl_mocks


class ApplyOrganizationPlanTests(unittest.TestCase):

    def setUp(self):
        self.mocks = install_fl_mocks()
        # Re-import the handlers module so it picks up the fresh fake FL modules.
        import importlib
        if "handlers_organize" in sys.modules:
            importlib.reload(sys.modules["handlers_organize"])
        if "handlers_bulk" in sys.modules:
            importlib.reload(sys.modules["handlers_bulk"])
        import handlers_bulk
        self.handlers_bulk = handlers_bulk

    def tearDown(self):
        uninstall_fl_mocks()

    def test_calls_save_undo_once_before_any_setter(self):
        plan = {
            "channels": [{"index": 0, "name": "KICK"}],
            "mixer_tracks": [{"index": 1, "name": "Drums Bus"}],
        }
        self.handlers_bulk._cmd_apply_organization_plan(plan)
        general_calls = self.mocks["general"].calls
        save_undos = [c for c in general_calls if c[0] == "saveUndo"]
        self.assertEqual(len(save_undos), 1, "saveUndo must be called exactly once")
        # First general call must be saveUndo
        self.assertEqual(general_calls[0][0], "saveUndo")
        self.assertEqual(general_calls[0][1], "Studio AI: Organize")

    def test_partial_success_collects_errors_and_continues(self):
        plan = {
            "channels": [
                {"index": 0, "name": "VALID"},
                {"index": "not-an-int", "name": "BAD"},
                {"index": 2, "color": 0xFF0000},
            ],
        }
        result = self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertEqual(result["applied"]["channels"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["entity"], "channels")
        self.assertEqual(result["errors"][0]["field"], "index")

    def test_empty_sections_no_calls(self):
        result = self.handlers_bulk._cmd_apply_organization_plan({})
        self.assertEqual(result["applied"],
                         {"channels": 0, "mixer_tracks": 0, "playlist_tracks": 0, "patterns": 0})
        self.assertEqual(result["errors"], [])
        # saveUndo still called exactly once (cheap, harmless empty undo step)
        self.assertEqual(
            sum(1 for c in self.mocks["general"].calls if c[0] == "saveUndo"), 1)

    def test_no_op_item_index_only_is_skipped(self):
        plan = {"channels": [{"index": 5}]}
        result = self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertEqual(result["applied"]["channels"], 0)
        self.assertEqual(result["errors"], [])
        # No setters should have run
        self.assertEqual(self.mocks["channels"].calls, [])

    def test_response_includes_undo_label_and_op_count(self):
        plan = {"channels": [{"index": 0, "name": "X", "color": 0x00FF00}]}
        result = self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertEqual(result["undo_label"], "Studio AI: Organize")
        self.assertTrue(result["undo_grouped"])
        self.assertEqual(result["op_count"], 2)  # name + color

    def test_plan_too_large_raises_value_error(self):
        # 2001 items total — must raise so the dispatch loop surfaces an error response
        plan = {"channels": [{"index": i, "name": "c{}".format(i)} for i in range(2001)]}
        with self.assertRaises(ValueError) as ctx:
            self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertIn("PLAN_TOO_LARGE", str(ctx.exception))
        # Bridge must not have touched FL
        self.assertEqual(self.mocks["channels"].calls, [])
        self.assertEqual(self.mocks["general"].calls, [])

    def test_save_undo_unavailable_falls_back_gracefully(self):
        # Simulate older FL: drop saveUndo from the general module
        delattr(self.mocks["general"], "saveUndo")
        plan = {"channels": [{"index": 0, "name": "Y"}]}
        result = self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertFalse(result["undo_grouped"])
        self.assertEqual(result["op_count"], 1)
        self.assertEqual(result["applied"]["channels"], 1)

    def test_save_undo_raises_falls_back(self):
        self.mocks["general"]._save_undo_should_raise = True
        plan = {"channels": [{"index": 0, "name": "Z"}]}
        result = self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertFalse(result["undo_grouped"])
        self.assertEqual(result["applied"]["channels"], 1)

    def test_indexing_conventions_per_section(self):
        # Channels/mixer 0-indexed; playlist/patterns 1-indexed.
        # The handler does not enforce indexing — it forwards whatever index
        # it receives to the underlying setter. This test pins that contract.
        plan = {
            "channels":         [{"index": 0, "name": "ch0"}],
            "mixer_tracks":     [{"index": 0, "name": "mx0"}],
            "playlist_tracks":  [{"index": 1, "name": "pl1"}],
            "patterns":         [{"index": 1, "name": "pat1"}],
        }
        self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertIn(("setChannelName", 0, "ch0"), self.mocks["channels"].calls)
        self.assertIn(("setTrackName", 0, "mx0"), self.mocks["mixer"].calls)
        self.assertIn(("setTrackName", 1, "pl1"), self.mocks["playlist"].calls)
        self.assertIn(("setPatternName", 1, "pat1"), self.mocks["patterns"].calls)


class UndoAndSaveTests(unittest.TestCase):

    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_organize" in sys.modules:
            importlib.reload(sys.modules["handlers_organize"])
        if "handlers_bulk" in sys.modules:
            importlib.reload(sys.modules["handlers_bulk"])
        import handlers_bulk
        self.handlers_bulk = handlers_bulk

    def tearDown(self):
        uninstall_fl_mocks()

    def test_undo_default_count_one(self):
        result = self.handlers_bulk._cmd_undo({})
        self.assertEqual(result, {"undone": True, "steps": 1})
        undos = [c for c in self.mocks["general"].calls if c[0] == "undoUp"]
        self.assertEqual(len(undos), 1)

    def test_undo_with_count(self):
        result = self.handlers_bulk._cmd_undo({"count": 3})
        self.assertEqual(result, {"undone": True, "steps": 3})
        undos = [c for c in self.mocks["general"].calls if c[0] == "undoUp"]
        self.assertEqual(len(undos), 3)

    def test_undo_count_clamps_to_at_least_one(self):
        result = self.handlers_bulk._cmd_undo({"count": 0})
        self.assertEqual(result["steps"], 1)

    def test_undo_handles_none_params(self):
        result = self.handlers_bulk._cmd_undo(None)
        self.assertEqual(result["steps"], 1)

    def test_save_project_calls_save_with_zero(self):
        result = self.handlers_bulk._cmd_save_project({})
        self.assertEqual(result, {"saved": True})
        self.assertIn(("saveProject", 0), self.mocks["general"].calls)


class HybridScoringTests(unittest.TestCase):

    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_bulk" in sys.modules:
            importlib.reload(sys.modules["handlers_bulk"])
        import handlers_bulk
        self.handlers_bulk = handlers_bulk

    def tearDown(self):
        uninstall_fl_mocks()

    def test_score_exact_match(self):
        self.assertEqual(self.handlers_bulk._score("kick", "Kick"), 1.0)

    def test_score_substring_boost_short_in_long(self):
        # "kick" (4 chars) in "Kick Layer Sub" (14 chars) → 0.7 + 0.3*(4/14)
        s = self.handlers_bulk._score("kick", "Kick Layer Sub")
        self.assertGreaterEqual(s, 0.78)
        self.assertLessEqual(s, 0.79)

    def test_score_no_substring_falls_back_to_difflib(self):
        # No substring; difflib produces something <0.7
        s = self.handlers_bulk._score("zzzz", "abcdef")
        self.assertLess(s, 0.7)

    def test_score_empty_name(self):
        self.assertEqual(self.handlers_bulk._score("anything", ""), 0.0)

    def test_score_case_insensitive(self):
        self.assertEqual(self.handlers_bulk._score("KICK", "kick"), 1.0)


class FindByNameTests(unittest.TestCase):

    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_bulk" in sys.modules:
            importlib.reload(sys.modules["handlers_bulk"])
        import handlers_bulk
        self.handlers_bulk = handlers_bulk

    def tearDown(self):
        uninstall_fl_mocks()

    def _seed_channels(self, names):
        ch = self.mocks["channels"]
        for i, n in enumerate(names):
            ch.names[i] = n

    def test_find_channel_basic_substring(self):
        self._seed_channels(["Kick", "Snare", "Kick Layer", "Hat", "Bass"])
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": "kick"})
        names = [m["name"] for m in result["matches"]]
        self.assertIn("Kick", names)
        self.assertIn("Kick Layer", names)
        self.assertNotIn("Snare", names)

    def test_find_sorted_by_score_desc_then_index_asc(self):
        # Two equal-score names → earlier index first
        self._seed_channels(["Kick", "Snare", "Kick"])
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": "kick"})
        # Both "Kick" entries score 1.0; index 0 must precede index 2
        kick_matches = [m for m in result["matches"] if m["name"] == "Kick"]
        self.assertEqual([m["index"] for m in kick_matches], [0, 2])

    def test_find_omits_below_cutoff(self):
        self._seed_channels(["Snare", "Hat", "Bass"])
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": "kick"})
        self.assertEqual(result["matches"], [])

    def test_find_default_limit_is_5(self):
        self._seed_channels(["Kick"] * 10)
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": "kick"})
        self.assertEqual(len(result["matches"]), 5)

    def test_find_explicit_limit(self):
        self._seed_channels(["Kick"] * 10)
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": "kick", "limit": 2})
        self.assertEqual(len(result["matches"]), 2)

    def test_find_empty_query_returns_empty(self):
        self._seed_channels(["Kick", "Snare"])
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": ""})
        self.assertEqual(result["matches"], [])

    def test_find_mixer_track_uses_zero_indexed_iteration(self):
        mx = self.mocks["mixer"]
        mx._track_count = 3
        mx.names = {0: "Master", 1: "Drums Bus", 2: "Bass Bus"}
        result = self.handlers_bulk._cmd_find_mixer_track_by_name({"query": "drums"})
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["index"], 1)

    def test_find_playlist_track_uses_one_indexed_iteration(self):
        pl = self.mocks["playlist"]
        pl._track_count = 3
        pl.names = {1: "Verse", 2: "Chorus", 3: "Bridge"}
        result = self.handlers_bulk._cmd_find_playlist_track_by_name({"query": "verse"})
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["index"], 1)  # 1-indexed

    def test_find_handles_throwing_getter(self):
        # Simulate a getter that raises on one index
        ch = self.mocks["channels"]
        ch.names = {0: "Kick", 1: "Snare"}
        def getChannelName(i):
            if i == 1:
                raise RuntimeError("simulated FL hiccup")
            return ch.names.get(i, "")
        ch.getChannelName = getChannelName
        result = self.handlers_bulk._cmd_find_channel_by_name({"query": "kick"})
        # Index 1 was skipped; "Kick" still found
        names = [m["name"] for m in result["matches"]]
        self.assertIn("Kick", names)


class HandlerRegistryTests(unittest.TestCase):
    """Pin the public action names of BULK_HANDLERS — these are the relay
    contracts the web app ships against. A rename here is a breaking change.
    """

    def setUp(self):
        install_fl_mocks()
        import importlib
        if "handlers_bulk" in sys.modules:
            importlib.reload(sys.modules["handlers_bulk"])
        import handlers_bulk
        self.handlers_bulk = handlers_bulk

    def tearDown(self):
        uninstall_fl_mocks()

    def test_bulk_handlers_action_names(self):
        self.assertEqual(
            sorted(self.handlers_bulk.BULK_HANDLERS.keys()),
            [
                "apply_organization_plan",
                "find_channel_by_name",
                "find_mixer_track_by_name",
                "find_playlist_track_by_name",
                "save_project",
                "undo",
            ],
        )


if __name__ == "__main__":
    unittest.main()
