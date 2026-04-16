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


# Real FL Studio 21 (MIDI API v40) returns a signed 32-bit int for
# getTrackColor/getPatternColor on untouched slots — NOT 0. The high byte is
# typically set (theme default), so `value & 0xFFFFFF` yields a non-zero gray
# (observed ~0x636C71 in the wild). -10261391 == (0xFF636C71 as int32). Tests
# use this to reproduce the bug where `color == 0` never matches and 500
# default playlist slots leak into the response, ballooning the IPC payload.
FL_DEFAULT_COLOR_SIGNED = -10261391


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

    # ── FL-default-color regression (bug: n=500/500 on real projects) ────────
    #
    # In production the handler kept ALL 500 default playlist slots (and all
    # 127 mixer tracks, and many patterns) because FL Studio's getTrackColor /
    # getPatternColor return the theme-default gray for untouched slots, not 0.
    # The old `color == 0` check never matched, so filtering was effectively
    # disabled and responses ballooned to ~30KB — near the macOS pipe buffer
    # limit, causing the partial-write pain addressed by commit 3193b37.
    #
    # These tests pin the fix: the handler must treat the theme default color
    # as "untouched" regardless of its specific value.

    def test_playlist_skips_tracks_with_fl_default_color(self):
        """All 500 playlist slots have FL's default (non-zero) color — skip all."""
        self.mocks["playlist"]._default_color = FL_DEFAULT_COLOR_SIGNED
        result, _ = self._call()
        self.assertEqual(result["playlist_tracks"], [])

    def test_playlist_keeps_custom_colored_track_when_default_is_nonzero(self):
        """Track 3 is user-colored red; the other 499 have FL's default gray.
        Only track 3 should survive the filter."""
        self.mocks["playlist"]._default_color = FL_DEFAULT_COLOR_SIGNED
        self.mocks["playlist"].colors = {3: 0xFF0000}
        result, _ = self._call()
        indices = [t["index"] for t in result["playlist_tracks"]]
        self.assertEqual(indices, [3])

    def test_playlist_keeps_named_track_when_default_color_nonzero(self):
        """User-named track with default color must still survive."""
        self.mocks["playlist"]._default_color = FL_DEFAULT_COLOR_SIGNED
        self.mocks["playlist"].names = {7: "Drums"}
        result, _ = self._call()
        indices = [t["index"] for t in result["playlist_tracks"]]
        self.assertEqual(indices, [7])

    def test_mixer_skips_tracks_with_fl_default_color(self):
        """All 127 mixer inserts have FL's default color — only Master (0)
        survives (explicit keep, not filter match)."""
        self.mocks["mixer"]._default_color = FL_DEFAULT_COLOR_SIGNED
        result, _ = self._call()
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertEqual(indices, [0])

    def test_mixer_keeps_custom_colored_track_when_default_is_nonzero(self):
        self.mocks["mixer"]._default_color = FL_DEFAULT_COLOR_SIGNED
        self.mocks["mixer"].colors = {10: 0xFF0000}
        result, _ = self._call()
        indices = [t["index"] for t in result["mixer_tracks"]]
        self.assertIn(0, indices)   # Master always kept
        self.assertIn(10, indices)  # User-colored kept
        self.assertEqual(len(indices), 2)

    def test_patterns_skips_slots_with_fl_default_color(self):
        """Default patterns should be filtered even when their color is the
        theme default (non-zero) rather than literal 0."""
        self.mocks["patterns"]._default_color = FL_DEFAULT_COLOR_SIGNED
        result, _ = self._call()
        self.assertEqual(result["patterns"], [])

    def test_patterns_keeps_named_pattern_when_default_color_nonzero(self):
        self.mocks["patterns"]._default_color = FL_DEFAULT_COLOR_SIGNED
        self.mocks["patterns"].names = {2: "Main Groove"}
        result, _ = self._call()
        indices = [p["index"] for p in result["patterns"]]
        self.assertEqual(indices, [2])

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
