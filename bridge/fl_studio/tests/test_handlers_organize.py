# bridge/fl_studio/tests/test_handlers_organize.py
"""Unit tests for handlers_organize.py — runs outside FL Studio with mocks.

The key handler under test here is `_cmd_get_project_state`, which used to
silently time out the plugin IPC because it makes ~2000 FL API calls on a
typical project. These tests cover:

- structural correctness of the response
- default-slot filtering (mixer/playlist/patterns skip uncolored defaults)
- timing diagnostic print output (captured via stdout), which is the
  operator's only window into *why* the plugin timeout fires when it does
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import install_fl_mocks, uninstall_fl_mocks


class GetProjectStateTests(unittest.TestCase):
    def setUp(self):
        self.mocks = install_fl_mocks()
        import importlib
        if "handlers_organize" in sys.modules:
            importlib.reload(sys.modules["handlers_organize"])
        import handlers_organize
        self.handler = handlers_organize._cmd_get_project_state

    def tearDown(self):
        uninstall_fl_mocks()

    def _call(self):
        """Call the handler, swallowing the timing-diagnostic stdout line."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = self.handler({})
        return result, buf.getvalue()

    # ── structural ──────────────────────────────────────────────────────────

    def test_returns_expected_top_level_keys(self):
        # Add one channel so channels isn't empty
        self.mocks["channels"].names = {0: "Kick"}
        self.mocks["channels"].colors = {0: 0xFF0000}
        result, _ = self._call()
        for key in ("bpm", "project_name", "playing",
                    "channels", "mixer_tracks", "playlist_tracks", "patterns"):
            self.assertIn(key, result)

    def test_bpm_converted_from_milli_bpm(self):
        # Mock returns 128000 → 128.0
        result, _ = self._call()
        self.assertEqual(result["bpm"], 128.0)

    def test_channels_returned_in_full_regardless_of_default(self):
        # 3 channels, all default-named — must still appear because they
        # only exist if the user added them.
        self.mocks["channels"].names = {0: "", 1: "", 2: ""}
        result, _ = self._call()
        self.assertEqual(len(result["channels"]), 3)

    def test_mixer_filters_default_named_uncolored_tracks(self):
        # 127 mixer tracks default — none named or colored. Only Master (0)
        # should survive the filter because i != 0 short-circuits skip.
        result, _ = self._call()
        # Master (index 0) has default name "" which _is_default_mixer_name
        # treats as default → still returned since i==0 is explicit keep.
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertEqual(indices, [0])

    def test_mixer_keeps_named_track(self):
        self.mocks["mixer"].names = {5: "Drums Bus"}
        result, _ = self._call()
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertIn(5, indices)

    def test_mixer_keeps_colored_track(self):
        self.mocks["mixer"].colors = {10: 0xFF0000}
        result, _ = self._call()
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertIn(10, indices)

    def test_playlist_filters_default_uncolored_tracks(self):
        # 500 default playlist tracks — all skipped
        result, _ = self._call()
        self.assertEqual(result["playlist_tracks"], [])

    def test_patterns_filters_default_uncolored(self):
        result, _ = self._call()
        self.assertEqual(result["patterns"], [])

    # ── timing diagnostic ───────────────────────────────────────────────────

    def test_timing_log_emitted_with_expected_fields(self):
        """The timing diagnostic is the *only* signal that tells us *where*
        the handler is spending its budget when the plugin IPC times out.
        Without this line in Script Output, a timeout is unactionable."""
        _, stdout = self._call()
        self.assertIn("get_project_state timing", stdout)
        # Every section should have a timing field so operators can spot
        # which one is blowing the budget.
        for section in ("meta=", "channels=", "mixer=", "playlist=", "patterns=", "total="):
            self.assertIn(section, stdout)

    def test_timing_log_single_line(self):
        # The FL Script Output window is tight; keep the log on one line so
        # it doesn't swamp other diagnostics.
        _, stdout = self._call()
        non_empty = [ln for ln in stdout.splitlines() if ln.strip()]
        self.assertEqual(len(non_empty), 1)


if __name__ == "__main__":
    unittest.main()
