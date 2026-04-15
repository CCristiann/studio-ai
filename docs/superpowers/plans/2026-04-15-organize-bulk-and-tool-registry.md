# Organize Bulk Apply + Tool Registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 new AI tools (bulk apply, undo, save, 3 find-by-name) so the organize agent can rename + recolor up to ~2,000 FL Studio entities in a single round-trip with one undo step, and refactor the inline tool definitions in `route.ts` into a per-domain registry under `lib/ai/tools/`.

**Architecture:** Per-domain TS modules export tool factories (`channelTools(userId)`, `mixerTools(userId)`, …), each backed by a shared `relayTool()` helper that DRYs the try/catch + RelayError mapping. New Python handlers live in `bridge/fl_studio/handlers_bulk.py` and reuse the existing per-item setters from `handlers_organize.py`. The bulk apply wraps every setter inside a single `general.saveUndo("Studio AI: Organize", 0)` so one Ctrl-Z reverts an entire batch. Hybrid scoring (substring boost + difflib ratio) handles `find_*_by_name` queries because pure SequenceMatcher is too strict for natural single-word lookups.

**Tech Stack:** Python 3 stdlib (`unittest`, `difflib`); FL Studio Python API (`general`, `channels`, `mixer`, `playlist`, `patterns`); TypeScript with Vercel AI SDK 6.x (`tool`, `streamText`, `stepCountIs`); Vitest for new TS unit tests; `@ai-sdk/google` for Gemini 2.5 Flash.

**Spec:** `docs/superpowers/specs/2026-04-15-organize-bulk-and-tool-registry-design.md`

---

## File Map

### New files (create)

| File | Responsibility |
|------|---------------|
| `bridge/fl_studio/handlers_bulk.py` | Six new handlers + `BULK_HANDLERS` dict |
| `bridge/fl_studio/tests/conftest.py` | FL module mocks (`general`, `channels`, `mixer`, `playlist`, `patterns`) |
| `bridge/fl_studio/tests/test_handlers_bulk.py` | unittest suite covering all six handlers |
| `apps/web/vitest.config.ts` | Vitest config (jsdom env, alias to `@/`) |
| `apps/web/src/lib/ai/tools/_shared.ts` | `relayTool()` helper + `RelayToolDef` type |
| `apps/web/src/lib/ai/tools/transport.ts` | `set_bpm`, `play`, `stop`, `set_pitch` |
| `apps/web/src/lib/ai/tools/channels.ts` | Channel tools incl. `find_channel_by_name` |
| `apps/web/src/lib/ai/tools/mixer.ts` | Mixer tools incl. `find_mixer_track_by_name` |
| `apps/web/src/lib/ai/tools/playlist.ts` | Playlist tools incl. `find_playlist_track_by_name` |
| `apps/web/src/lib/ai/tools/patterns.ts` | `rename_pattern`, `set_pattern_color` |
| `apps/web/src/lib/ai/tools/project.ts` | `get_project_state`, `save_project`, `undo` |
| `apps/web/src/lib/ai/tools/organize.ts` | `apply_organization_plan`, `organize_project` (legacy wrap), `scaffold_project` (legacy wrap) |
| `apps/web/src/lib/ai/tools/index.ts` | `composeTools(userId)` aggregator |
| `apps/web/src/lib/ai/tools/__tests__/_shared.test.ts` | Tests for `relayTool` shape |
| `apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts` | Snapshot of tool keys + descriptions |
| `apps/web/src/lib/ai/system-prompt.ts` | System prompt string, exported as `SYSTEM_PROMPT` |

### Modified files

| File | What changes |
|------|--------------|
| `bridge/fl_studio/device_studio_ai.py` | Import `BULK_HANDLERS`, spread into `_HANDLERS` |
| `apps/web/src/app/api/ai/execute/route.ts` | Reduced to ~80 lines: `composeTools(userId)` + `streamText` |
| `apps/web/package.json` | Add `vitest`, `@vitejs/plugin-react`, `jsdom` to devDependencies |

### Deleted files

| File | Why |
|------|-----|
| `apps/web/src/lib/ai/organize/analysis-agent.ts` | Replaced by direct `get_project_state` tool call from main loop |
| `apps/web/src/lib/ai/organize/execute-plan.ts` | Replaced by bridge-side `_cmd_apply_organization_plan` |

### Files preserved (still referenced)

- `apps/web/src/lib/ai/organize/expand-plan.ts` — still useful for normalizing legacy `organize_project` plans during the migration window
- `apps/web/src/lib/ai/organize/organization-agent.ts` — `runOrganization` and `runScaffold` retained for the legacy `organize_project` and `scaffold_project` wrappers in Phase 2; only deleted in a follow-up if usage drops to zero
- `apps/web/src/lib/ai/organize/types.ts`, `colors.ts`, `prompts.ts` — still imported by `organization-agent.ts`

---

## Phase Overview

| Phase | Tasks | Goal |
|-------|-------|------|
| **1: Bridge** | 1 – 5 | New Python handlers land with full unit coverage. Wired into device script. Verifiable in isolation. |
| **2: Registry refactor** | 6 – 11 | Existing tools moved out of `route.ts` into per-domain modules. Zero behavior change. Snapshot test guards regression. |
| **3: New TS tools** | 12 – 14 | Add the six new tools to the registry. Update system prompt. Simplify legacy organize agent. |
| **4: Verification** | 15 | Manual smoke test on real FL Studio. Activate undo-grouping fallback if needed. |

Each phase is independently shippable. After every phase, the build is green and the app works.

---

## Phase 1 — Bridge

### Task 1: Bridge test scaffolding (FL module mocks)

**Files:**
- Create: `bridge/fl_studio/tests/conftest.py`

The bridge handlers `import general`, `import channels`, etc., lazily at runtime inside FL Studio. To exercise them in unittest we install fake modules into `sys.modules` before the handler runs.

- [ ] **Step 1: Create `conftest.py` with reusable FL module fakes**

```python
# bridge/fl_studio/tests/conftest.py
"""Shared test scaffolding: fake FL Studio modules.

Imported automatically by pytest. Even if you run unittest directly,
import this file at the top of each test module.

Each fake exposes the subset of the real FL API that handlers_bulk.py
and handlers_organize.py call. Tests can replace any attribute on the
fake to simulate specific FL state or to assert calls.
"""
import sys
import types
from collections import defaultdict


def _make_general_mock():
    mod = types.ModuleType("general")
    mod.calls = []  # ordered call log
    mod._save_undo_supported = True
    mod._save_undo_should_raise = False

    def saveUndo(label, flags=0):
        mod.calls.append(("saveUndo", label, flags))
        if mod._save_undo_should_raise:
            raise RuntimeError("simulated FL refusal")

    def undoUp():
        mod.calls.append(("undoUp",))

    def saveProject(mode):
        mod.calls.append(("saveProject", mode))

    def getProjectTitle():
        return "TestProject"

    def processRECEvent(event_id, value, flags):
        mod.calls.append(("processRECEvent", event_id, value, flags))

    mod.saveUndo = saveUndo
    mod.undoUp = undoUp
    mod.saveProject = saveProject
    mod.getProjectTitle = getProjectTitle
    mod.processRECEvent = processRECEvent
    return mod


def _make_channels_mock():
    mod = types.ModuleType("channels")
    mod.names = {}        # {index: name}
    mod.colors = {}       # {index: int}
    mod.inserts = {}      # {index: int}
    mod.muted = {}        # {index: bool}
    mod.calls = []

    def channelCount():
        return len(mod.names)

    def getChannelName(i):
        return mod.names.get(i, "")

    def setChannelName(i, name):
        mod.calls.append(("setChannelName", i, name))
        mod.names[i] = name

    def getChannelColor(i):
        return mod.colors.get(i, 0)

    def setChannelColor(i, color):
        mod.calls.append(("setChannelColor", i, color))
        mod.colors[i] = color

    def setTargetFxTrack(i, insert):
        mod.calls.append(("setTargetFxTrack", i, insert))
        mod.inserts[i] = insert

    def getTargetFxTrack(i):
        return mod.inserts.get(i, 0)

    def isChannelMuted(i):
        return mod.muted.get(i, False)

    def muteChannel(i):
        mod.calls.append(("muteChannel", i))
        mod.muted[i] = not mod.muted.get(i, False)

    def getChannelVolume(i):
        return 0.78

    def setChannelVolume(i, v):
        mod.calls.append(("setChannelVolume", i, v))

    def getChannelPan(i):
        return 0.0

    def setChannelPan(i, p):
        mod.calls.append(("setChannelPan", i, p))

    def getGridBit(i, step):
        return 0

    def getGridBitWithoutCache(i, step):
        return 0

    mod.channelCount = channelCount
    mod.getChannelName = getChannelName
    mod.setChannelName = setChannelName
    mod.getChannelColor = getChannelColor
    mod.setChannelColor = setChannelColor
    mod.setTargetFxTrack = setTargetFxTrack
    mod.getTargetFxTrack = getTargetFxTrack
    mod.isChannelMuted = isChannelMuted
    mod.muteChannel = muteChannel
    mod.getChannelVolume = getChannelVolume
    mod.setChannelVolume = setChannelVolume
    mod.getChannelPan = getChannelPan
    mod.setChannelPan = setChannelPan
    mod.getGridBit = getGridBit
    mod.getGridBitWithoutCache = getGridBitWithoutCache
    return mod


def _make_mixer_mock():
    mod = types.ModuleType("mixer")
    mod.names = {}
    mod.colors = {}
    mod.calls = []
    mod._track_count = 127  # FL 20+ default

    def trackCount():
        return mod._track_count

    def getTrackName(i):
        return mod.names.get(i, "")

    def setTrackName(i, name):
        mod.calls.append(("setTrackName", i, name))
        mod.names[i] = name

    def getTrackColor(i):
        return mod.colors.get(i, 0)

    def setTrackColor(i, color):
        mod.calls.append(("setTrackColor", i, color))
        mod.colors[i] = color

    def getCurrentTempo():
        return 128000

    def isTrackMuted(i):
        return False

    def isTrackSolo(i):
        return False

    def getTrackVolume(i):
        return 0.8

    def getTrackPan(i):
        return 0.0

    def setRouteTo(a, b, on):
        mod.calls.append(("setRouteTo", a, b, on))

    def setTrackEQGain(*args):
        mod.calls.append(("setTrackEQGain",) + args)

    def setTrackEQFreq(*args):
        mod.calls.append(("setTrackEQFreq",) + args)

    def setTrackEQBW(*args):
        mod.calls.append(("setTrackEQBW",) + args)

    mod.trackCount = trackCount
    mod.getTrackName = getTrackName
    mod.setTrackName = setTrackName
    mod.getTrackColor = getTrackColor
    mod.setTrackColor = setTrackColor
    mod.getCurrentTempo = getCurrentTempo
    mod.isTrackMuted = isTrackMuted
    mod.isTrackSolo = isTrackSolo
    mod.getTrackVolume = getTrackVolume
    mod.getTrackPan = getTrackPan
    mod.setRouteTo = setRouteTo
    mod.setTrackEQGain = setTrackEQGain
    mod.setTrackEQFreq = setTrackEQFreq
    mod.setTrackEQBW = setTrackEQBW
    return mod


def _make_playlist_mock():
    mod = types.ModuleType("playlist")
    mod.names = {}        # 1-indexed
    mod.colors = {}       # 1-indexed
    mod.calls = []
    mod._track_count = 500

    def trackCount():
        return mod._track_count

    def getTrackName(i):
        return mod.names.get(i, "")

    def setTrackName(i, name):
        mod.calls.append(("setTrackName", i, name))
        mod.names[i] = name

    def getTrackColor(i):
        return mod.colors.get(i, 0)

    def setTrackColor(i, color):
        mod.calls.append(("setTrackColor", i, color))
        mod.colors[i] = color

    mod.trackCount = trackCount
    mod.getTrackName = getTrackName
    mod.setTrackName = setTrackName
    mod.getTrackColor = getTrackColor
    mod.setTrackColor = setTrackColor
    return mod


def _make_patterns_mock():
    mod = types.ModuleType("patterns")
    mod.names = {}        # 1-indexed
    mod.colors = {}       # 1-indexed
    mod.calls = []
    mod._pattern_count = 999

    def patternCount():
        return mod._pattern_count

    def getPatternName(i):
        return mod.names.get(i, "")

    def setPatternName(i, name):
        mod.calls.append(("setPatternName", i, name))
        mod.names[i] = name

    def getPatternColor(i):
        return mod.colors.get(i, 0)

    def setPatternColor(i, color):
        mod.calls.append(("setPatternColor", i, color))
        mod.colors[i] = color

    mod.patternCount = patternCount
    mod.getPatternName = getPatternName
    mod.setPatternName = setPatternName
    mod.getPatternColor = getPatternColor
    mod.setPatternColor = setPatternColor
    return mod


def install_fl_mocks():
    """Install fresh FL module mocks for one test. Returns dict for assertions."""
    mocks = {
        "general": _make_general_mock(),
        "channels": _make_channels_mock(),
        "mixer": _make_mixer_mock(),
        "playlist": _make_playlist_mock(),
        "patterns": _make_patterns_mock(),
    }
    for name, mod in mocks.items():
        sys.modules[name] = mod
    # Also a stub midi module since handlers_organize uses it
    midi_mod = types.ModuleType("midi")
    midi_mod.REC_MainPitch = 0
    midi_mod.REC_Tempo = 1
    midi_mod.REC_Control = 2
    midi_mod.REC_UpdateControl = 4
    sys.modules["midi"] = midi_mod
    sys.modules["transport"] = types.ModuleType("transport")
    sys.modules["transport"].isPlaying = lambda: False
    return mocks


def uninstall_fl_mocks():
    for name in ("general", "channels", "mixer", "playlist", "patterns", "midi", "transport"):
        sys.modules.pop(name, None)
```

- [ ] **Step 2: Verify the file is importable**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -c "import sys; sys.path.insert(0, 'tests'); from conftest import install_fl_mocks, uninstall_fl_mocks; m = install_fl_mocks(); print('mocks OK:', list(m.keys())); uninstall_fl_mocks()"
```

Expected: `mocks OK: ['general', 'channels', 'mixer', 'playlist', 'patterns']`

- [ ] **Step 3: Commit**

```bash
git add bridge/fl_studio/tests/conftest.py
git commit -m "test(bridge): scaffold FL Studio module mocks for unit tests"
```

---

### Task 2: `_cmd_apply_organization_plan` — TDD

**Files:**
- Create: `bridge/fl_studio/handlers_bulk.py` (initial: only `apply_organization_plan` + `BULK_HANDLERS`)
- Create: `bridge/fl_studio/tests/test_handlers_bulk.py`

- [ ] **Step 1: Write failing tests for `_cmd_apply_organization_plan`**

```python
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

    def test_plan_too_large_returns_early(self):
        # 2001 items total
        plan = {"channels": [{"index": i, "name": f"c{i}"} for i in range(2001)]}
        result = self.handlers_bulk._cmd_apply_organization_plan(plan)
        self.assertFalse(result.get("success", True))
        self.assertEqual(result.get("error"), "PLAN_TOO_LARGE")
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail (handlers_bulk.py does not exist yet)**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest tests.test_handlers_bulk -v
```

Expected: `ModuleNotFoundError: No module named 'handlers_bulk'`

- [ ] **Step 3: Create minimal `handlers_bulk.py` with `_cmd_apply_organization_plan`**

```python
# bridge/fl_studio/handlers_bulk.py
"""Bulk apply, undo, save, find-by-name handlers for Studio AI.

Imported by device_studio_ai.py via:
    from handlers_bulk import BULK_HANDLERS

FL Studio Python modules are imported lazily inside each handler because
they're only available at runtime inside FL Studio's Python environment.
"""
import difflib

from handlers_organize import (
    _cmd_rename_channel, _cmd_set_channel_color, _cmd_set_channel_insert,
    _cmd_rename_mixer_track, _cmd_set_mixer_track_color,
    _cmd_rename_playlist_track, _cmd_set_playlist_track_color,
    _cmd_rename_pattern, _cmd_set_pattern_color,
)

UNDO_LABEL = "Studio AI: Organize"
PLAN_ITEM_CAP = 2000              # hard cap to stay under 5s relay timeout
FIND_SCORE_CUTOFF = 0.6           # below this, omit entirely


def _cmd_apply_organization_plan(params):
    """Apply a structured plan in a single FL undo step.

    Returns:
      { applied: {section: count}, errors: [...], undo_label: str,
        undo_grouped: bool, op_count: int }

    `undo_grouped=False` means general.saveUndo was unavailable on this FL
    version — the AI should issue `undo` `op_count` times to fully revert.
    """
    import general

    plan = params or {}

    # Item-cap guardrail before touching FL (5s relay timeout protection).
    total_items = sum(
        len(plan.get(k) or [])
        for k in ("channels", "mixer_tracks", "playlist_tracks", "patterns")
    )
    if total_items > PLAN_ITEM_CAP:
        return {
            "success": False,
            "error": "PLAN_TOO_LARGE",
            "limit": PLAN_ITEM_CAP,
            "got": total_items,
            "suggestion": (
                "Plan has {} items, exceeds {} cap. "
                "Split into smaller batches (each its own undo step)."
            ).format(total_items, PLAN_ITEM_CAP),
        }

    applied = {"channels": 0, "mixer_tracks": 0, "playlist_tracks": 0, "patterns": 0}
    errors = []
    op_count = [0]  # boxed for closure mutation under Py 2/3 stdlib

    # Group everything under a single undo entry IF saveUndo is available.
    undo_grouped = hasattr(general, "saveUndo")
    if undo_grouped:
        try:
            general.saveUndo(UNDO_LABEL, 0)
        except Exception:
            undo_grouped = False  # FL refused; fall back

    def _apply_section(section_key, items, field_handlers):
        for item in items or []:
            try:
                idx = int(item["index"])
            except (KeyError, ValueError, TypeError):
                errors.append({
                    "entity": section_key, "index": -1, "field": "index",
                    "message": "missing or invalid index",
                })
                continue
            touched = False
            for field, handler in field_handlers.items():
                if field in item and item[field] is not None:
                    try:
                        handler({"index": idx, field: item[field]})
                        touched = True
                        op_count[0] += 1
                    except Exception as e:
                        errors.append({
                            "entity": section_key, "index": idx,
                            "field": field, "message": str(e),
                        })
            if touched:
                applied[section_key] += 1

    _apply_section("channels", plan.get("channels"), {
        "name":   lambda p: _cmd_rename_channel({"index": p["index"], "name": p["name"]}),
        "color":  lambda p: _cmd_set_channel_color({"index": p["index"], "color": p["color"]}),
        "insert": lambda p: _cmd_set_channel_insert({"index": p["index"], "insert": p["insert"]}),
    })
    _apply_section("mixer_tracks", plan.get("mixer_tracks"), {
        "name":  lambda p: _cmd_rename_mixer_track({"index": p["index"], "name": p["name"]}),
        "color": lambda p: _cmd_set_mixer_track_color({"index": p["index"], "color": p["color"]}),
    })
    _apply_section("playlist_tracks", plan.get("playlist_tracks"), {
        "name":  lambda p: _cmd_rename_playlist_track({"index": p["index"], "name": p["name"]}),
        "color": lambda p: _cmd_set_playlist_track_color({"index": p["index"], "color": p["color"]}),
    })
    _apply_section("patterns", plan.get("patterns"), {
        "name":  lambda p: _cmd_rename_pattern({"index": p["index"], "name": p["name"]}),
        "color": lambda p: _cmd_set_pattern_color({"index": p["index"], "color": p["color"]}),
    })

    return {
        "applied": applied,
        "errors": errors,
        "undo_label": UNDO_LABEL,
        "undo_grouped": undo_grouped,
        "op_count": op_count[0],
    }


BULK_HANDLERS = {
    "apply_organization_plan": _cmd_apply_organization_plan,
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest tests.test_handlers_bulk -v
```

Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add bridge/fl_studio/handlers_bulk.py bridge/fl_studio/tests/test_handlers_bulk.py
git commit -m "feat(bridge): apply_organization_plan handler with undo grouping"
```

---

### Task 3: `_cmd_undo` and `_cmd_save_project` — TDD

**Files:**
- Modify: `bridge/fl_studio/handlers_bulk.py` (add two handlers + register)
- Modify: `bridge/fl_studio/tests/test_handlers_bulk.py` (add a new TestCase)

- [ ] **Step 1: Write failing tests for undo + save**

Append to `bridge/fl_studio/tests/test_handlers_bulk.py`:

```python
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest tests.test_handlers_bulk.UndoAndSaveTests -v
```

Expected: `AttributeError: module 'handlers_bulk' has no attribute '_cmd_undo'`

- [ ] **Step 3: Add `_cmd_undo` and `_cmd_save_project` to `handlers_bulk.py`**

Append to `bridge/fl_studio/handlers_bulk.py` (just before `BULK_HANDLERS`):

```python
def _cmd_undo(params):
    """Undo the most recent FL action.

    If params.count is provided (used when undo_grouped=False from a prior
    apply), undoUp is called that many times. Default 1.
    """
    import general
    count = max(1, int((params or {}).get("count", 1)))
    for _ in range(count):
        general.undoUp()
    return {"undone": True, "steps": count}


def _cmd_save_project(_params):
    """Save the current FL project. mode=0 = save in-place (silent if a path
    is set; FL prompts the user only for an untitled project).
    """
    import general
    general.saveProject(0)
    return {"saved": True}
```

Update `BULK_HANDLERS` at the bottom of the file:

```python
BULK_HANDLERS = {
    "apply_organization_plan": _cmd_apply_organization_plan,
    "undo":                    _cmd_undo,
    "save_project":            _cmd_save_project,
}
```

- [ ] **Step 4: Run the full test file to verify everything passes**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest tests.test_handlers_bulk -v
```

Expected: All tests pass (9 from Task 2 + 5 new = 14 total).

- [ ] **Step 5: Commit**

```bash
git add bridge/fl_studio/handlers_bulk.py bridge/fl_studio/tests/test_handlers_bulk.py
git commit -m "feat(bridge): undo + save_project handlers"
```

---

### Task 4: `find_*_by_name` handlers + hybrid scoring — TDD

**Files:**
- Modify: `bridge/fl_studio/handlers_bulk.py` (add three handlers + `_score`/`_rank_matches`)
- Modify: `bridge/fl_studio/tests/test_handlers_bulk.py` (add new TestCases)

- [ ] **Step 1: Write failing tests for hybrid scoring + find handlers**

Append to `bridge/fl_studio/tests/test_handlers_bulk.py`:

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest tests.test_handlers_bulk.HybridScoringTests tests.test_handlers_bulk.FindByNameTests -v
```

Expected: `AttributeError: module 'handlers_bulk' has no attribute '_score'` (or similar).

- [ ] **Step 3: Add `_score`, `_rank_matches`, and three `_cmd_find_*_by_name` handlers**

Append to `bridge/fl_studio/handlers_bulk.py` (before `BULK_HANDLERS`):

```python
def _score(query, name):
    """Hybrid match: substring boost + difflib SequenceMatcher fallback.

    Pure SequenceMatcher.ratio is too strict for the dominant query case
    where the user types one word and expects to match a longer name
    (e.g. "kick" vs "Kick Layer Sub"). Substring matches earn a 0.7
    baseline, scaled up by query coverage of the candidate.
    """
    q = (query or "").lower()
    n = (name or "").lower()
    if not n:
        return 0.0
    if q in n:
        return round(0.7 + 0.3 * (len(q) / len(n)), 3)
    return round(difflib.SequenceMatcher(None, q, n).ratio(), 3)


def _rank_matches(query, candidates, limit, cutoff=FIND_SCORE_CUTOFF):
    """Score candidates against query, sort, return top N above cutoff."""
    scored = []
    for index, name in candidates:
        s = _score(query, name)
        if s >= cutoff:
            scored.append({"index": index, "name": name, "score": s})
    scored.sort(key=lambda m: (-m["score"], m["index"]))
    return scored[:limit]


def _cmd_find_channel_by_name(params):
    import channels
    query = str((params or {}).get("query", "")).strip()
    limit = int((params or {}).get("limit", 5))
    if not query:
        return {"matches": []}
    candidates = []
    for i in range(channels.channelCount()):
        try:
            name = channels.getChannelName(i) or ""
        except Exception:
            continue
        candidates.append((i, name))
    return {"matches": _rank_matches(query, candidates, limit)}


def _cmd_find_mixer_track_by_name(params):
    import mixer
    query = str((params or {}).get("query", "")).strip()
    limit = int((params or {}).get("limit", 5))
    if not query:
        return {"matches": []}
    candidates = []
    for i in range(mixer.trackCount()):
        try:
            name = mixer.getTrackName(i) or ""
        except Exception:
            continue
        candidates.append((i, name))
    return {"matches": _rank_matches(query, candidates, limit)}


def _cmd_find_playlist_track_by_name(params):
    import playlist
    query = str((params or {}).get("query", "")).strip()
    limit = int((params or {}).get("limit", 5))
    if not query:
        return {"matches": []}
    candidates = []
    for i in range(1, playlist.trackCount() + 1):  # 1-indexed
        try:
            name = playlist.getTrackName(i) or ""
        except Exception:
            continue
        candidates.append((i, name))
    return {"matches": _rank_matches(query, candidates, limit)}
```

Update `BULK_HANDLERS`:

```python
BULK_HANDLERS = {
    "apply_organization_plan":      _cmd_apply_organization_plan,
    "undo":                         _cmd_undo,
    "save_project":                 _cmd_save_project,
    "find_channel_by_name":         _cmd_find_channel_by_name,
    "find_mixer_track_by_name":     _cmd_find_mixer_track_by_name,
    "find_playlist_track_by_name":  _cmd_find_playlist_track_by_name,
}
```

- [ ] **Step 4: Run all tests to verify everything passes**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest tests.test_handlers_bulk -v
```

Expected: All tests pass (14 from earlier + 5 scoring + 9 find = 28 total).

- [ ] **Step 5: Commit**

```bash
git add bridge/fl_studio/handlers_bulk.py bridge/fl_studio/tests/test_handlers_bulk.py
git commit -m "feat(bridge): find_*_by_name handlers with hybrid substring+difflib scoring"
```

---

### Task 5: Wire `BULK_HANDLERS` into `device_studio_ai.py`

**Files:**
- Modify: `bridge/fl_studio/device_studio_ai.py:49` (add import) and `bridge/fl_studio/device_studio_ai.py:323-337` (extend `_HANDLERS`)

- [ ] **Step 1: Add the import line**

Edit `bridge/fl_studio/device_studio_ai.py` line 49:

```python
from handlers_organize import ORGANIZE_HANDLERS
from handlers_bulk import BULK_HANDLERS
```

- [ ] **Step 2: Spread `BULK_HANDLERS` into the registry**

Edit the `_HANDLERS` dict at the bottom of `device_studio_ai.py` (currently lines 323-337). Change the trailing line from:

```python
    **ORGANIZE_HANDLERS,
}
```

to:

```python
    **ORGANIZE_HANDLERS,
    **BULK_HANDLERS,
}
```

- [ ] **Step 3: Add a smoke test for the registry composition**

Append to `bridge/fl_studio/tests/test_handlers_bulk.py`:

```python
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
```

- [ ] **Step 4: Run all bridge tests**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/bridge/fl_studio
python3 -m unittest discover tests -v
```

Expected: All tests pass (existing protocol tests + 28 bulk tests + 1 registry test = 29+).

- [ ] **Step 5: Commit**

```bash
git add bridge/fl_studio/device_studio_ai.py bridge/fl_studio/tests/test_handlers_bulk.py
git commit -m "feat(bridge): wire BULK_HANDLERS into device_studio_ai handler registry"
```

---

## Phase 2 — Tool registry refactor (no behavior change)

The goal of this phase: pull every existing tool out of the inline `route.ts` definition into per-domain modules, with **byte-for-byte identical Zod schemas, descriptions, and execute behavior**. The snapshot test in Task 11 enforces that.

### Task 6: Add Vitest as a dev dependency + initial config

**Files:**
- Modify: `apps/web/package.json`
- Create: `apps/web/vitest.config.ts`

- [ ] **Step 1: Install Vitest and friends**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai
pnpm add -D vitest @vitejs/plugin-react jsdom --filter web
```

Expected: `apps/web/package.json` gains `vitest`, `@vitejs/plugin-react`, `jsdom` under `devDependencies`.

- [ ] **Step 2: Create `apps/web/vitest.config.ts`**

```ts
// apps/web/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    globals: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

- [ ] **Step 3: Add a `test` script to `apps/web/package.json`**

Edit the `"scripts"` block in `apps/web/package.json`:

```json
"scripts": {
  "dev": "next dev --turbopack",
  "build": "next build",
  "start": "next start",
  "lint": "next lint",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

- [ ] **Step 4: Verify Vitest runs (no tests yet → green)**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run
```

Expected: `No test files found` — exits 0 (or with a friendly "no tests" message). If it exits non-zero, add `--passWithNoTests` to the script and re-run.

- [ ] **Step 5: Commit**

```bash
git add apps/web/package.json apps/web/vitest.config.ts pnpm-lock.yaml
git commit -m "chore(web): add vitest, @vitejs/plugin-react, jsdom for AI tools tests"
```

---

### Task 7: `_shared.ts` — `relayTool()` helper + tests

**Files:**
- Create: `apps/web/src/lib/ai/tools/_shared.ts`
- Create: `apps/web/src/lib/ai/tools/__tests__/_shared.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/src/lib/ai/tools/__tests__/_shared.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { z } from "zod";

// Mock @/lib/relay BEFORE importing _shared
vi.mock("@/lib/relay", () => {
  class RelayError extends Error {
    code: string;
    statusCode: number;
    constructor(code: string, message: string, statusCode: number) {
      super(message);
      this.name = "RelayError";
      this.code = code;
      this.statusCode = statusCode;
    }
  }
  return {
    relay: vi.fn(),
    RelayError,
  };
});

import { relay, RelayError } from "@/lib/relay";
import { relayTool } from "../_shared";

const mockedRelay = vi.mocked(relay);

describe("relayTool", () => {
  beforeEach(() => {
    mockedRelay.mockReset();
  });

  it("forwards input through toRelay() and returns success on relay success", async () => {
    mockedRelay.mockResolvedValue({
      id: "x",
      success: true,
      data: { bpm: 128 },
    });
    const t = relayTool("user-1", {
      description: "set bpm",
      inputSchema: z.object({ bpm: z.number() }),
      toRelay: ({ bpm }) => ({ action: "set_bpm", params: { bpm } }),
    });
    const result = await t.execute!({ bpm: 128 }, {} as any);
    expect(mockedRelay).toHaveBeenCalledWith("user-1", "set_bpm", { bpm: 128 });
    expect(result).toEqual({ success: true, data: { bpm: 128 } });
  });

  it("applies mapResult when provided", async () => {
    mockedRelay.mockResolvedValue({ id: "x", success: true, data: { bpm: 128 } });
    const t = relayTool("u", {
      description: "set bpm with bpm-only result",
      inputSchema: z.object({ bpm: z.number() }),
      toRelay: ({ bpm }) => ({ action: "set_bpm", params: { bpm } }),
      mapResult: (data, input) => ({ before: input.bpm, after: (data as any).bpm }),
    });
    const result = await t.execute!({ bpm: 128 }, {} as any);
    expect(result).toEqual({
      success: true,
      data: { before: 128, after: 128 },
    });
  });

  it("returns success:false with the relay's error on relay-level failure", async () => {
    mockedRelay.mockResolvedValue({
      id: "x",
      success: false,
      data: null,
      error: "DAW says no",
    });
    const t = relayTool("u", {
      description: "x",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "noop", params: {} }),
    });
    const result = await t.execute!({}, {} as any);
    expect(result).toEqual({ success: false, error: "DAW says no" });
  });

  it("maps RelayError to {success:false, error, code}", async () => {
    mockedRelay.mockRejectedValue(new RelayError("DAW_TIMEOUT", "timed out", 504));
    const t = relayTool("u", {
      description: "x",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "noop", params: {} }),
    });
    const result = await t.execute!({}, {} as any);
    expect(result).toEqual({ success: false, error: "timed out", code: "DAW_TIMEOUT" });
  });

  it("maps unknown errors to a generic message", async () => {
    mockedRelay.mockRejectedValue(new Error("network blew up"));
    const t = relayTool("u", {
      description: "x",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "noop", params: {} }),
    });
    const result = await t.execute!({}, {} as any);
    expect(result).toEqual({ success: false, error: "Failed to relay command" });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails (no `_shared.ts` yet)**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run src/lib/ai/tools/__tests__/_shared.test.ts
```

Expected: `Failed to load url ../_shared` — module not found.

- [ ] **Step 3: Create `_shared.ts`**

```ts
// apps/web/src/lib/ai/tools/_shared.ts
import { tool } from "ai";
import type { ZodTypeAny, z } from "zod";
import { relay, RelayError } from "@/lib/relay";

export interface RelayToolDef<TInput extends ZodTypeAny> {
  description: string;
  inputSchema: TInput;
  /** Map AI tool input → relay action name + params. */
  toRelay: (input: z.infer<TInput>) => { action: string; params: Record<string, unknown> };
  /** Optionally transform the relay's data before returning to the AI. */
  mapResult?: (data: unknown, input: z.infer<TInput>) => unknown;
}

/**
 * Wrap an FL-bridge relay call as a Vercel AI SDK tool.
 *
 * Centralizes the success/RelayError/unknown-error response shape so every
 * tool returns the same `{ success, data?, error?, code? }` envelope.
 */
export function relayTool<TInput extends ZodTypeAny>(
  userId: string,
  def: RelayToolDef<TInput>,
) {
  return tool({
    description: def.description,
    inputSchema: def.inputSchema,
    execute: async (input: z.infer<TInput>) => {
      const { action, params } = def.toRelay(input);
      try {
        const result = await relay(userId, action, params);
        if (!result.success) {
          return { success: false, error: result.error };
        }
        return {
          success: true,
          data: def.mapResult ? def.mapResult(result.data, input) : result.data,
        };
      } catch (e) {
        if (e instanceof RelayError) {
          return { success: false, error: e.message, code: e.code };
        }
        return { success: false, error: "Failed to relay command" };
      }
    },
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run src/lib/ai/tools/__tests__/_shared.test.ts
```

Expected: All 5 tests pass.

- [ ] **Step 5: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/ai/tools/_shared.ts apps/web/src/lib/ai/tools/__tests__/_shared.test.ts
git commit -m "feat(ai): relayTool() helper for AI tool definitions"
```

---

### Task 8: Extract transport + project tools

**Files:**
- Create: `apps/web/src/lib/ai/tools/transport.ts`
- Create: `apps/web/src/lib/ai/tools/project.ts`

- [ ] **Step 1: Create `transport.ts`** — `set_bpm`, `play`, `stop`, `set_pitch`

```ts
// apps/web/src/lib/ai/tools/transport.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function transportTools(userId: string) {
  return {
    set_bpm: relayTool(userId, {
      description: "Set the BPM (tempo) of the current project. Valid range: 10-999.",
      inputSchema: z.object({
        bpm: z.number().min(10).max(999).describe("The BPM to set"),
      }),
      toRelay: ({ bpm }) => ({ action: "set_bpm", params: { bpm } }),
      mapResult: (_data, { bpm }) => ({ bpm }),
    }),

    play: relayTool(userId, {
      description: "Start playback in the DAW.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "play", params: {} }),
      mapResult: () => ({}),
    }),

    stop: relayTool(userId, {
      description: "Stop playback in the DAW.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "stop", params: {} }),
      mapResult: () => ({}),
    }),

    set_pitch: relayTool(userId, {
      description: "Set the project's master pitch in semitones (-12 to +12). Use when the user asks to transpose the whole project up or down.",
      inputSchema: z.object({
        semitones: z.number().min(-12).max(12).describe("Semitones to transpose (-12 to +12)"),
      }),
      toRelay: ({ semitones }) => ({ action: "set_pitch", params: { semitones } }),
    }),
  };
}
```

> NOTE on `mapResult`: The original `play`/`stop` tools returned `{ success: true }` (no `data` field). `relayTool` always returns `{ success: true, data }`. The `mapResult: () => ({})` keeps `data` as an empty object — schema-equivalent for the model. Snapshot test in Task 11 verifies this is acceptable.

- [ ] **Step 2: Create `project.ts`** — `get_project_state`

```ts
// apps/web/src/lib/ai/tools/project.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description: "Get the current state of the DAW project including BPM, tracks, and project name.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "get_state", params: {} }),
    }),
  };
}
```

> NOTE: The current `route.ts` calls relay action `"get_state"` (not `"get_project_state"`) because `device_studio_ai.py` aliases both to `_cmd_get_state`. We preserve this exact behavior — Phase 3 Task 12 will optionally swap the action to `"get_project_state"` for the richer payload.

- [ ] **Step 3: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/ai/tools/transport.ts apps/web/src/lib/ai/tools/project.ts
git commit -m "refactor(ai): extract transport + project tools to dedicated modules"
```

---

### Task 9: Extract channels + mixer tools

**Files:**
- Create: `apps/web/src/lib/ai/tools/channels.ts`
- Create: `apps/web/src/lib/ai/tools/mixer.ts`

- [ ] **Step 1: Create `channels.ts`** — `set_channel_volume`, `set_channel_pan`, `set_channel_enabled`

```ts
// apps/web/src/lib/ai/tools/channels.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const CH_INDEX = z.number().int().min(0).max(999).describe("Channel rack index (0-indexed)");

export function channelTools(userId: string) {
  return {
    set_channel_volume: relayTool(userId, {
      description: "Set a channel rack entry's volume (0.0 to 1.0, where ~0.78 is unity).",
      inputSchema: z.object({
        index: CH_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({
        action: "set_channel_volume",
        params: { index, volume },
      }),
    }),

    set_channel_pan: relayTool(userId, {
      description: "Set a channel rack entry's stereo pan (-1.0 = hard left, 0 = center, 1.0 = hard right).",
      inputSchema: z.object({
        index: CH_INDEX,
        pan: z.number().min(-1).max(1).describe("Pan (-1.0 to 1.0)"),
      }),
      toRelay: ({ index, pan }) => ({
        action: "set_channel_pan",
        params: { index, pan },
      }),
    }),

    set_channel_enabled: relayTool(userId, {
      description: "Enable or disable (mute) a channel rack entry.",
      inputSchema: z.object({
        index: CH_INDEX,
        enabled: z.boolean().describe("true to enable, false to mute"),
      }),
      toRelay: ({ index, enabled }) => ({
        action: "set_channel_enabled",
        params: { index, enabled },
      }),
    }),
  };
}
```

- [ ] **Step 2: Create `mixer.ts`** — `set_track_volume`, `set_mixer_routing`, `set_mixer_eq`

```ts
// apps/web/src/lib/ai/tools/mixer.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const MX_INDEX = z.number().int().min(0).max(126).describe("Mixer track index (0=Master, 1-125=Inserts, 126=Current)");

export function mixerTools(userId: string) {
  return {
    set_track_volume: relayTool(userId, {
      description: "Set a mixer track's volume level.",
      inputSchema: z.object({
        index: MX_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({
        action: "set_track_volume",
        params: { index, volume },
      }),
    }),

    set_mixer_routing: relayTool(userId, {
      description: "Route a mixer track's output to another mixer track. Use enabled=false to remove an existing route.",
      inputSchema: z.object({
        from_index: z.number().int().min(0).max(126).describe("Source mixer track"),
        to_index: z.number().int().min(0).max(126).describe("Destination mixer track"),
        enabled: z.boolean().default(true).describe("true to create the route, false to remove it"),
      }),
      toRelay: ({ from_index, to_index, enabled }) => ({
        action: "set_mixer_routing",
        params: { from_index, to_index, enabled },
      }),
    }),

    set_mixer_eq: relayTool(userId, {
      description: "Adjust a mixer track's 3-band parametric EQ. Specify which band (low/mid/high) and any combination of gain, freq, and bw. All values are normalized 0.0–1.0 (gain 0.5 = unity).",
      inputSchema: z.object({
        index: MX_INDEX,
        band: z.enum(["low", "mid", "high"]).describe("EQ band to adjust"),
        gain: z.number().min(0).max(1).optional().describe("Normalized gain (0.5 = unity)"),
        freq: z.number().min(0).max(1).optional().describe("Normalized frequency"),
        bw: z.number().min(0).max(1).optional().describe("Normalized bandwidth / Q"),
      }),
      toRelay: ({ index, band, gain, freq, bw }) => ({
        action: "set_mixer_eq",
        params: { index, band, gain, freq, bw },
      }),
    }),
  };
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/ai/tools/channels.ts apps/web/src/lib/ai/tools/mixer.ts
git commit -m "refactor(ai): extract channel + mixer tools to dedicated modules"
```

---

### Task 10: Extract organize wrappers (legacy `organize_project`, `scaffold_project`)

**Files:**
- Create: `apps/web/src/lib/ai/tools/organize.ts`
- Create: `apps/web/src/lib/ai/tools/playlist.ts` (placeholder for Phase 3)
- Create: `apps/web/src/lib/ai/tools/patterns.ts` (placeholder for Phase 3)

The two legacy tools (`organize_project`, `scaffold_project`) do not fit the simple `relayTool` shape — they orchestrate multiple agent calls. So we keep their existing inline implementations but pull them into a dedicated module. This task is pure code motion.

- [ ] **Step 1: Create `playlist.ts` and `patterns.ts` placeholders**

```ts
// apps/web/src/lib/ai/tools/playlist.ts
export function playlistTools(_userId: string) {
  return {};
}
```

```ts
// apps/web/src/lib/ai/tools/patterns.ts
export function patternTools(_userId: string) {
  return {};
}
```

These are non-empty placeholders so `composeTools` can spread them; new tools land here in Phase 3.

- [ ] **Step 2: Create `organize.ts` with the existing `organize_project` and `scaffold_project` bodies**

```ts
// apps/web/src/lib/ai/tools/organize.ts
import { tool } from "ai";
import { z } from "zod";
import { relay } from "@/lib/relay";
import { runAnalysis } from "@/lib/ai/organize/analysis-agent";
import { runOrganization, runScaffold } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { executePlan } from "@/lib/ai/organize/execute-plan";
import type { EnhancedProjectState } from "@studio-ai/types";

export function organizeTools(userId: string) {
  return {
    organize_project: tool({
      description: "Analyze and organize the current FL Studio project. Reads the project state, classifies channels by musical role (drums, bass, leads, pads, fx, vocals), then renames and color-codes everything consistently. Shows a preview before applying. Use when the user asks to organize, clean up, or color-code their project.",
      inputSchema: z.object({
        confirm: z.boolean().default(false).describe("Set to true to apply the plan after previewing. First call with false to preview, then true to apply."),
      }),
      execute: async (input) => {
        try {
          if (!input.confirm) {
            const { projectMap, projectState } = await runAnalysis(userId);
            const aiPlan = await runOrganization(projectMap, projectState);
            const fullPlan = expandPlan(aiPlan, projectState);
            return {
              success: true,
              status: "preview",
              preview: fullPlan.preview,
              actionCount: fullPlan.actions.length,
              _aiPlan: aiPlan,
              _projectState: projectState,
            };
          } else {
            const { projectMap, projectState } = await runAnalysis(userId);
            const aiPlan = await runOrganization(projectMap, projectState);
            const fullPlan = expandPlan(aiPlan, projectState);
            const result = await executePlan(userId, fullPlan);
            return {
              success: result.failures.length === 0,
              status: "applied",
              completedActions: result.completedActions,
              totalActions: result.totalActions,
              failures: result.failures.length > 0
                ? result.failures.map(f => `${f.action.type}(${JSON.stringify(f.action.params)}): ${f.error}`)
                : undefined,
            };
          }
        } catch (e) {
          return { success: false, error: e instanceof Error ? e.message : "Organization failed" };
        }
      },
    }),

    scaffold_project: tool({
      description: "Set up a new FL Studio project template based on a genre or style. Renames and color-codes the existing channels in the project to match the genre. Note: FL Studio cannot add channels programmatically, so the template is limited to the number of channels already in the project. Use when the user says they're starting a new beat/track and mentions a genre or style.",
      inputSchema: z.object({
        genre: z.string().describe("Genre or style description, e.g. 'trap beat', 'lo-fi hip hop', 'dark drill with 808s'"),
        confirm: z.boolean().default(false).describe("Set to true to apply the template after previewing."),
      }),
      execute: async (input) => {
        try {
          const stateResult = await relay(userId, "get_project_state", {});
          if (!stateResult.success) {
            return { success: false, error: "Could not read project state" };
          }
          const projectState = stateResult.data as EnhancedProjectState | undefined;
          if (!projectState?.channels) {
            return { success: false, error: "Project state is empty — open a project with channels in the Channel Rack." };
          }
          const channelCount = projectState.channels.length;

          const aiPlan = await runScaffold(input.genre);
          const trimmedPlan = {
            ...aiPlan,
            channelAssignments: aiPlan.channelAssignments
              .slice(0, channelCount)
              .map((a, i) => ({ ...a, index: projectState.channels[i].index })),
          };

          const fullPlan = expandPlan(trimmedPlan, projectState);

          if (!input.confirm) {
            const skipped = aiPlan.channelAssignments.length - trimmedPlan.channelAssignments.length;
            return {
              success: true,
              status: "preview",
              genre: input.genre,
              preview: fullPlan.preview,
              actionCount: fullPlan.actions.length,
              channelsAvailable: channelCount,
              channelsRequested: aiPlan.channelAssignments.length,
              ...(skipped > 0 && {
                note: `Your project has ${channelCount} channels but the template needs ${aiPlan.channelAssignments.length}. ${skipped} channels were skipped. Add more channels in FL Studio first if you want the full template.`,
              }),
            };
          } else {
            const result = await executePlan(userId, fullPlan);
            return {
              success: result.failures.length === 0,
              status: "applied",
              genre: input.genre,
              completedActions: result.completedActions,
              totalActions: result.totalActions,
              failures: result.failures.length > 0
                ? result.failures.map(f => `${f.action.type}(${JSON.stringify(f.action.params)}): ${f.error}`)
                : undefined,
            };
          }
        } catch (e) {
          return { success: false, error: e instanceof Error ? e.message : "Scaffold failed" };
        }
      },
    }),
  };
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/ai/tools/playlist.ts apps/web/src/lib/ai/tools/patterns.ts apps/web/src/lib/ai/tools/organize.ts
git commit -m "refactor(ai): extract organize_project + scaffold_project to organize.ts"
```

---

### Task 11: `tools/index.ts` (composeTools) + snapshot regression test

**Files:**
- Create: `apps/web/src/lib/ai/tools/index.ts`
- Create: `apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts`

- [ ] **Step 1: Write the failing snapshot test**

```ts
// apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/relay", () => ({
  relay: vi.fn(),
  RelayError: class extends Error {},
}));

// organize.ts pulls in heavy modules; mock them so the import doesn't crash
vi.mock("@/lib/ai/organize/analysis-agent", () => ({ runAnalysis: vi.fn() }));
vi.mock("@/lib/ai/organize/organization-agent", () => ({
  runOrganization: vi.fn(),
  runScaffold: vi.fn(),
  adjustPlan: vi.fn(),
}));
vi.mock("@/lib/ai/organize/expand-plan", () => ({ expandPlan: vi.fn() }));
vi.mock("@/lib/ai/organize/execute-plan", () => ({
  executePlan: vi.fn(),
  validateStateBeforeExecution: vi.fn(),
}));

import { composeTools } from "../index";

describe("composeTools", () => {
  it("exposes the migrated tool set with stable names", () => {
    const tools = composeTools("user-1");
    const names = Object.keys(tools).sort();
    // Pinned: changing this list is a public-contract change. Update intentionally.
    expect(names).toEqual([
      "get_project_state",
      "organize_project",
      "play",
      "scaffold_project",
      "set_bpm",
      "set_channel_enabled",
      "set_channel_pan",
      "set_channel_volume",
      "set_mixer_eq",
      "set_mixer_routing",
      "set_pitch",
      "set_track_volume",
      "stop",
    ]);
  });

  it("every tool has a non-empty description", () => {
    const tools = composeTools("user-1");
    for (const [name, t] of Object.entries(tools)) {
      expect((t as any).description, `${name} description`).toBeTruthy();
      expect(typeof (t as any).description).toBe("string");
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails (no `index.ts` yet)**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run src/lib/ai/tools/__tests__/composeTools.test.ts
```

Expected: `Failed to load url ../index` — module not found.

- [ ] **Step 3: Create `index.ts`**

```ts
// apps/web/src/lib/ai/tools/index.ts
import { transportTools } from "./transport";
import { channelTools }  from "./channels";
import { mixerTools }    from "./mixer";
import { playlistTools } from "./playlist";
import { patternTools }  from "./patterns";
import { projectTools }  from "./project";
import { organizeTools } from "./organize";

export function composeTools(userId: string) {
  return {
    ...transportTools(userId),
    ...channelTools(userId),
    ...mixerTools(userId),
    ...playlistTools(userId),
    ...patternTools(userId),
    ...projectTools(userId),
    ...organizeTools(userId),
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run src/lib/ai/tools/__tests__/composeTools.test.ts
```

Expected: Both tests pass.

- [ ] **Step 5: Run the entire test suite to confirm no regressions**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run
```

Expected: All tests pass (5 from `_shared.test.ts` + 2 from `composeTools.test.ts` = 7 total).

- [ ] **Step 6: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/ai/tools/index.ts apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts
git commit -m "feat(ai): composeTools() aggregator with snapshot regression guard"
```

---

### Task 12: Refactor `route.ts` to use `composeTools` + extract system prompt

**Files:**
- Create: `apps/web/src/lib/ai/system-prompt.ts`
- Modify: `apps/web/src/app/api/ai/execute/route.ts` (replace 398 lines with ~30)

- [ ] **Step 1: Create `system-prompt.ts` with the existing prompt verbatim**

```ts
// apps/web/src/lib/ai/system-prompt.ts
/**
 * System prompt for the main /api/ai/execute endpoint.
 *
 * Edit here, not inline in route.ts, so prompt changes are diff-reviewable
 * in isolation and easy to grep for.
 */
export const SYSTEM_PROMPT = `You are Studio AI, an AI assistant that controls FL Studio through natural language.

You can:
- Set BPM, add tracks, control playback, adjust mixer volumes
- Organize existing projects: analyze channels, classify them by role (drums, bass, leads, pads, fx, vocals), then rename and color-code everything consistently
- Scaffold new projects: set up a genre-specific template with named, color-coded channels

When the user asks to organize or clean up their project, use organize_project with confirm=false first to show a preview, then confirm=true to apply.
When the user wants to start a new beat/track, use scaffold_project with the genre they describe — preview first, then apply.

Always present the preview clearly to the user before applying changes. Format the preview as a grouped list showing the color groups and channel names.`;
```

- [ ] **Step 2: Replace `route.ts` with the slim version**

Open `apps/web/src/app/api/ai/execute/route.ts`. Replace the entire file contents with:

```ts
import { streamText, stepCountIs, UIMessage, convertToModelMessages } from "ai";
import { google } from "@ai-sdk/google";
import { auth } from "@/lib/auth";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { rateLimit } from "@/lib/rate-limit";
import { composeTools } from "@/lib/ai/tools";
import { SYSTEM_PROMPT } from "@/lib/ai/system-prompt";

async function getUserId(req: Request): Promise<string | null> {
  // 1. Try Bearer token (plugin WebView)
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  // 2. Fall back to session cookie (browser dashboard)
  const session = await auth();
  return session?.userId ?? null;
}

export async function POST(req: Request) {
  const userId = await getUserId(req);
  if (!userId) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Rate limit: max 20 AI requests per user per minute
  const { success } = rateLimit(`ai:${userId}`, {
    limit: 20,
    windowMs: 60_000,
  });
  if (!success) {
    return new Response("Rate limit exceeded", { status: 429 });
  }

  const { messages }: { messages: UIMessage[] } = await req.json();

  const result = streamText({
    model: google("gemini-2.5-flash"),
    providerOptions: {
      google: { thinkingConfig: { thinkingBudget: 0 } },
    },
    system: SYSTEM_PROMPT,
    messages: await convertToModelMessages(messages),
    tools: composeTools(userId),
    stopWhen: stepCountIs(5),
  });

  return result.toUIMessageStreamResponse();
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Run the full TS test suite**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run
```

Expected: 7 tests still pass (regression check — no behavior should have changed).

- [ ] **Step 5: Manual sanity check — boot the dev server and exercise one tool**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai
./dev.sh
```

In another terminal:
```bash
curl -X POST http://localhost:3000/api/ai/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TEST_PLUGIN_TOKEN>" \
  -d '{"messages":[{"id":"1","role":"user","parts":[{"type":"text","text":"What is the current BPM?"}]}]}'
```

Expected: SSE stream comes back. The first tool call should be `get_project_state`. (If you don't have a plugin token handy, skip this step — the snapshot test already pinned the tool surface.)

Stop the dev server with Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/ai/system-prompt.ts apps/web/src/app/api/ai/execute/route.ts
git commit -m "refactor(ai): route.ts uses composeTools(); system prompt extracted"
```

---

## Phase 3 — New TS tools wired into the registry

### Task 13: Add new tools to per-domain modules

**Files:**
- Modify: `apps/web/src/lib/ai/tools/project.ts` (add `save_project`, `undo`)
- Modify: `apps/web/src/lib/ai/tools/channels.ts` (add granular per-item + `find_channel_by_name`)
- Modify: `apps/web/src/lib/ai/tools/mixer.ts` (add granular per-item + `find_mixer_track_by_name`)
- Create: replace placeholder `apps/web/src/lib/ai/tools/playlist.ts`
- Create: replace placeholder `apps/web/src/lib/ai/tools/patterns.ts`
- Modify: `apps/web/src/lib/ai/tools/organize.ts` (add `apply_organization_plan`)
- Modify: `apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts` (extend the pinned list)

- [ ] **Step 1: Update the snapshot test first to lock in the new public surface (TDD)**

Edit the pinned `expect(names).toEqual([...])` array in `composeTools.test.ts` to:

```ts
    expect(names).toEqual([
      "apply_organization_plan",
      "find_channel_by_name",
      "find_mixer_track_by_name",
      "find_playlist_track_by_name",
      "get_project_state",
      "organize_project",
      "play",
      "rename_channel",
      "rename_mixer_track",
      "rename_pattern",
      "rename_playlist_track",
      "save_project",
      "scaffold_project",
      "set_bpm",
      "set_channel_color",
      "set_channel_enabled",
      "set_channel_insert",
      "set_channel_pan",
      "set_channel_volume",
      "set_mixer_eq",
      "set_mixer_routing",
      "set_mixer_track_color",
      "set_pattern_color",
      "set_pitch",
      "set_playlist_track_color",
      "set_track_volume",
      "stop",
      "undo",
    ]);
```

- [ ] **Step 2: Run snapshot test to verify it fails (new tool names not present yet)**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run src/lib/ai/tools/__tests__/composeTools.test.ts
```

Expected: `expected … toEqual …` diff shows the new tools missing.

- [ ] **Step 3: Add `save_project` and `undo` to `project.ts`**

Replace `apps/web/src/lib/ai/tools/project.ts` with:

```ts
// apps/web/src/lib/ai/tools/project.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description: "Get the current state of the DAW project including BPM, tracks, and project name. Use this once at the start of any organize task to learn the project layout.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "get_state", params: {} }),
    }),

    save_project: relayTool(userId, {
      description: "Save the current FL Studio project. Use this as a checkpoint before bulk-organizing so the user can recover if they dislike the result.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "save_project", params: {} }),
    }),

    undo: relayTool(userId, {
      description: "Undo the most recent change in FL Studio (uses FL's native undo history). After applying an organization plan, this reverts the entire batch as one step. Pass `count` only when a previous `apply_organization_plan` returned `undo_grouped: false` — then pass that response's `op_count`.",
      inputSchema: z.object({
        count: z.number().int().min(1).max(2000).optional().describe("Number of undo steps. Default 1. Only set when a prior apply_organization_plan returned undo_grouped:false."),
      }),
      toRelay: ({ count }) => ({ action: "undo", params: count !== undefined ? { count } : {} }),
    }),
  };
}
```

- [ ] **Step 4: Add granular per-item + find tool to `channels.ts`**

Replace `apps/web/src/lib/ai/tools/channels.ts` with:

```ts
// apps/web/src/lib/ai/tools/channels.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const CH_INDEX = z.number().int().min(0).max(999).describe("Channel rack index (0-indexed)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF).describe("24-bit RGB color (e.g. 0xFF0000 = red)");

export function channelTools(userId: string) {
  return {
    rename_channel: relayTool(userId, {
      description: "Rename a single channel rack entry. For renaming many channels at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: CH_INDEX,
        name: z.string().min(1).max(128).describe("New name (1-128 chars)"),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_channel", params: { index, name } }),
    }),

    set_channel_color: relayTool(userId, {
      description: "Set the color of a single channel rack entry (24-bit RGB). For coloring many at once, prefer apply_organization_plan.",
      inputSchema: z.object({ index: CH_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_channel_color", params: { index, color } }),
    }),

    set_channel_insert: relayTool(userId, {
      description: "Route a channel rack entry to a mixer insert.",
      inputSchema: z.object({
        index: CH_INDEX,
        insert: z.number().int().min(0).max(126).describe("Mixer insert track (0=Master, 1-125=Inserts, 126=Current)"),
      }),
      toRelay: ({ index, insert }) => ({ action: "set_channel_insert", params: { index, insert } }),
    }),

    set_channel_volume: relayTool(userId, {
      description: "Set a channel rack entry's volume (0.0 to 1.0, where ~0.78 is unity).",
      inputSchema: z.object({
        index: CH_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({ action: "set_channel_volume", params: { index, volume } }),
    }),

    set_channel_pan: relayTool(userId, {
      description: "Set a channel rack entry's stereo pan (-1.0 = hard left, 0 = center, 1.0 = hard right).",
      inputSchema: z.object({
        index: CH_INDEX,
        pan: z.number().min(-1).max(1).describe("Pan (-1.0 to 1.0)"),
      }),
      toRelay: ({ index, pan }) => ({ action: "set_channel_pan", params: { index, pan } }),
    }),

    set_channel_enabled: relayTool(userId, {
      description: "Enable or disable (mute) a channel rack entry.",
      inputSchema: z.object({
        index: CH_INDEX,
        enabled: z.boolean().describe("true to enable, false to mute"),
      }),
      toRelay: ({ index, enabled }) => ({ action: "set_channel_enabled", params: { index, enabled } }),
    }),

    find_channel_by_name: relayTool(userId, {
      description: "Find channel rack entries by name (fuzzy substring match). Returns up to `limit` matches sorted by score. Use this to resolve user references like \"the kick\" before calling per-channel setters.",
      inputSchema: z.object({
        query: z.string().min(1).max(128).describe("Substring to search for (case-insensitive)"),
        limit: z.number().int().min(1).max(20).optional().default(5).describe("Max matches to return"),
      }),
      toRelay: ({ query, limit }) => ({ action: "find_channel_by_name", params: { query, limit } }),
    }),
  };
}
```

- [ ] **Step 5: Add granular + find tool to `mixer.ts`**

Replace `apps/web/src/lib/ai/tools/mixer.ts` with:

```ts
// apps/web/src/lib/ai/tools/mixer.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const MX_INDEX = z.number().int().min(0).max(126).describe("Mixer track index (0=Master, 1-125=Inserts, 126=Current)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF).describe("24-bit RGB color");

export function mixerTools(userId: string) {
  return {
    rename_mixer_track: relayTool(userId, {
      description: "Rename a single mixer track. For many at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: MX_INDEX,
        name: z.string().min(1).max(128).describe("New name (1-128 chars)"),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_mixer_track", params: { index, name } }),
    }),

    set_mixer_track_color: relayTool(userId, {
      description: "Set the color of a single mixer track (24-bit RGB).",
      inputSchema: z.object({ index: MX_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_mixer_track_color", params: { index, color } }),
    }),

    set_track_volume: relayTool(userId, {
      description: "Set a mixer track's volume level.",
      inputSchema: z.object({
        index: MX_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({ action: "set_track_volume", params: { index, volume } }),
    }),

    set_mixer_routing: relayTool(userId, {
      description: "Route a mixer track's output to another mixer track. Use enabled=false to remove an existing route.",
      inputSchema: z.object({
        from_index: z.number().int().min(0).max(126).describe("Source mixer track"),
        to_index: z.number().int().min(0).max(126).describe("Destination mixer track"),
        enabled: z.boolean().default(true).describe("true to create the route, false to remove it"),
      }),
      toRelay: ({ from_index, to_index, enabled }) => ({
        action: "set_mixer_routing",
        params: { from_index, to_index, enabled },
      }),
    }),

    set_mixer_eq: relayTool(userId, {
      description: "Adjust a mixer track's 3-band parametric EQ. Specify which band (low/mid/high) and any combination of gain, freq, and bw. All values are normalized 0.0–1.0 (gain 0.5 = unity).",
      inputSchema: z.object({
        index: MX_INDEX,
        band: z.enum(["low", "mid", "high"]).describe("EQ band to adjust"),
        gain: z.number().min(0).max(1).optional().describe("Normalized gain (0.5 = unity)"),
        freq: z.number().min(0).max(1).optional().describe("Normalized frequency"),
        bw: z.number().min(0).max(1).optional().describe("Normalized bandwidth / Q"),
      }),
      toRelay: ({ index, band, gain, freq, bw }) => ({
        action: "set_mixer_eq",
        params: { index, band, gain, freq, bw },
      }),
    }),

    find_mixer_track_by_name: relayTool(userId, {
      description: "Find mixer tracks by name (fuzzy substring match). Returns up to `limit` matches sorted by score. Use to resolve user references like \"the drum bus\".",
      inputSchema: z.object({
        query: z.string().min(1).max(128),
        limit: z.number().int().min(1).max(20).optional().default(5),
      }),
      toRelay: ({ query, limit }) => ({ action: "find_mixer_track_by_name", params: { query, limit } }),
    }),
  };
}
```

- [ ] **Step 6: Implement `playlist.ts`**

Replace `apps/web/src/lib/ai/tools/playlist.ts` with:

```ts
// apps/web/src/lib/ai/tools/playlist.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const PL_INDEX = z.number().int().min(1).max(500).describe("Playlist track index (1-indexed; FL 20+ caps at 500)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF);

export function playlistTools(userId: string) {
  return {
    rename_playlist_track: relayTool(userId, {
      description: "Rename a single playlist track (1-indexed). For many at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: PL_INDEX,
        name: z.string().min(1).max(128),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_playlist_track", params: { index, name } }),
    }),

    set_playlist_track_color: relayTool(userId, {
      description: "Set the color of a playlist track (1-indexed, 24-bit RGB).",
      inputSchema: z.object({ index: PL_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_playlist_track_color", params: { index, color } }),
    }),

    find_playlist_track_by_name: relayTool(userId, {
      description: "Find playlist tracks by name (fuzzy substring match, 1-indexed). Returns up to `limit` matches sorted by score.",
      inputSchema: z.object({
        query: z.string().min(1).max(128),
        limit: z.number().int().min(1).max(20).optional().default(5),
      }),
      toRelay: ({ query, limit }) => ({ action: "find_playlist_track_by_name", params: { query, limit } }),
    }),
  };
}
```

- [ ] **Step 7: Implement `patterns.ts`**

Replace `apps/web/src/lib/ai/tools/patterns.ts` with:

```ts
// apps/web/src/lib/ai/tools/patterns.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const PAT_INDEX = z.number().int().min(1).max(999).describe("Pattern index (1-indexed)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF);

export function patternTools(userId: string) {
  return {
    rename_pattern: relayTool(userId, {
      description: "Rename a single pattern (1-indexed). For many at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: PAT_INDEX,
        name: z.string().min(1).max(128),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_pattern", params: { index, name } }),
    }),

    set_pattern_color: relayTool(userId, {
      description: "Set the color of a pattern (1-indexed, 24-bit RGB).",
      inputSchema: z.object({ index: PAT_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_pattern_color", params: { index, color } }),
    }),
  };
}
```

- [ ] **Step 8: Add `apply_organization_plan` to `organize.ts`**

Edit `apps/web/src/lib/ai/tools/organize.ts`. Add the new imports at the top:

```ts
import { relayTool } from "./_shared";
```

Then **inside** the `organizeTools(userId)` return block, add `apply_organization_plan` as a new key (alongside the existing `organize_project` and `scaffold_project`):

```ts
    apply_organization_plan: relayTool(userId, {
      description: "Apply a structured rename + recolor + (channel only) insert-routing plan in a single FL Studio undo step. Use this for any organize task that touches more than 3 entities — it's one round-trip and one Ctrl+Z to revert. Each section is optional; omit sections you don't need to touch. Item fields are independent (you can pass name, color, or both). The whole apply registers as one undo step. If the response has `undo_grouped: false`, then `undo` must be called with `count: <op_count>` to fully revert.",
      inputSchema: z.object({
        channels: z.array(z.object({
          index: z.number().int().min(0).max(999).describe("0-indexed channel rack entry"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
          insert: z.number().int().min(0).max(126).optional().describe("Target mixer insert"),
        })).optional(),
        mixer_tracks: z.array(z.object({
          index: z.number().int().min(0).max(126).describe("0-indexed mixer track (0=Master, 1-125=Inserts, 126=Current)"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
        playlist_tracks: z.array(z.object({
          index: z.number().int().min(1).max(500).describe("1-indexed playlist track"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
        patterns: z.array(z.object({
          index: z.number().int().min(1).max(999).describe("1-indexed pattern"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
      }),
      toRelay: (plan) => ({ action: "apply_organization_plan", params: plan }),
    }),
```

- [ ] **Step 9: Run the snapshot test — should now pass**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run src/lib/ai/tools/__tests__/composeTools.test.ts
```

Expected: Both tests pass.

- [ ] **Step 10: Run the full TS test suite + type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run && bunx tsc --noEmit
```

Expected: All 7 tests pass; TS clean.

- [ ] **Step 11: Commit**

```bash
git add apps/web/src/lib/ai/tools/
git commit -m "feat(ai): add 6 new tools (apply_organization_plan, undo, save_project, find_*_by_name) + per-item granular setters"
```

---

### Task 14: Update system prompt for the new tools

**Files:**
- Modify: `apps/web/src/lib/ai/system-prompt.ts`

- [ ] **Step 1: Replace `system-prompt.ts` with the expanded prompt**

```ts
// apps/web/src/lib/ai/system-prompt.ts
/**
 * System prompt for the main /api/ai/execute endpoint.
 *
 * Edit here, not inline in route.ts, so prompt changes are diff-reviewable
 * in isolation and easy to grep for.
 */
export const SYSTEM_PROMPT = `You are Studio AI, an AI assistant that controls FL Studio through natural language for music producers.

# What you can do
- Set BPM, control playback (play/stop), transpose master pitch
- Read project state (channels, mixer tracks, playlist tracks, patterns)
- Rename and color channels, mixer tracks, playlist tracks, and patterns
- Adjust channel volume, pan, mute, mixer routing, mixer EQ
- Save the project, undo the last action

# Tool selection rules

## Organizing many entities at once
**For renaming or recoloring more than 3 entities, ALWAYS use \`apply_organization_plan\` in a single call** — not multiple per-item calls. This wraps the whole batch in one FL undo step (one Ctrl+Z reverts everything) and is one network round-trip.

Workflow:
1. Call \`get_project_state\` to learn the current layout.
2. Build a textual plan in chat. Show the user a grouped preview (e.g. "Drums: kick, snare, hat → red. Bass: sub, 808 → orange.").
3. After user confirmation, call \`save_project\` (checkpoint), then \`apply_organization_plan\` with the structured plan.
4. After applying, tell the user how many items changed and that they can type "undo" to revert.

If \`apply_organization_plan\` returns \`{ success: false, error: "PLAN_TOO_LARGE" }\`, split the plan into smaller batches (each ≤ 2000 items) and call apply repeatedly. Each batch is its own undo step.

If a successful apply returns \`undo_grouped: false\`, the older FL version couldn't group undos — to revert, call \`undo\` with \`count: <the response's op_count>\`.

## Single-entity tweaks
For "rename channel 3 to KICK" or "color the bass red", use the per-item tools (\`rename_channel\`, \`set_channel_color\`, etc.) — they're snappy and don't need a plan envelope.

## Resolving names
When the user references something by name ("the kick", "the drum bus"), call the matching \`find_*_by_name\` tool first to resolve to an index. If \`matches\` is empty, ask the user to clarify — never guess. If multiple matches with similar scores (within 0.05 of top), ask the user to disambiguate before acting.

## Legacy organize_project / scaffold_project
These older multi-stage tools are retained for backwards compatibility. **Prefer the new flow** (\`get_project_state\` → plan in chat → \`save_project\` → \`apply_organization_plan\`) for new conversations.

# Indexing conventions (FL Studio)
- Channel rack and mixer tracks: 0-indexed.
- Playlist tracks and patterns: 1-indexed.

# Tone
You're talking to a music producer. Be concise, direct, and use producer language. Don't over-explain music theory. When something fails, tell them what failed and what to try next.`;
```

- [ ] **Step 2: Type-check**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Run vitest (no test changes expected; just confirm nothing crashed at import)**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx vitest run
```

Expected: 7 tests pass.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/ai/system-prompt.ts
git commit -m "feat(ai): expand system prompt to teach the new bulk-apply flow"
```

---

### Task 15: Simplify legacy organize agent (delete `analysis-agent.ts` + `execute-plan.ts`)

The new flow makes `analysis-agent.ts` and `execute-plan.ts` unused — `runAnalysis` is replaced by a direct `get_project_state` tool call from the model, and `executePlan` is replaced by the bridge's `_cmd_apply_organization_plan`. The legacy `organize_project` and `scaffold_project` tools still exist (in `organize.ts`), so we keep `runOrganization`, `runScaffold`, `expandPlan` for now.

But wait — the legacy tools currently import `runAnalysis` and `executePlan`. We can't delete those files until we either:
(a) Remove the legacy tools, or
(b) Rewire them to use the new flow internally.

We pick **(b)**: keep `organize_project` and `scaffold_project` callable, but rewrite their internals to use the new bulk-apply path. This preserves the public tool surface (the snapshot test still passes) while removing dead helpers.

**Files:**
- Modify: `apps/web/src/lib/ai/tools/organize.ts` (rewire legacy tools to use new path)
- Delete: `apps/web/src/lib/ai/organize/analysis-agent.ts`
- Delete: `apps/web/src/lib/ai/organize/execute-plan.ts`

- [ ] **Step 1: Rewrite `organize_project` in `organize.ts` to use the new flow internally**

Edit `apps/web/src/lib/ai/tools/organize.ts`. Replace the entire file with:

```ts
// apps/web/src/lib/ai/tools/organize.ts
import { tool } from "ai";
import { z } from "zod";
import { relay } from "@/lib/relay";
import { relayTool } from "./_shared";
import { runOrganization, runScaffold } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import type { EnhancedProjectState, ProjectMap } from "@studio-ai/types";

/**
 * Convert an EnhancedProjectState (from get_project_state) into the simpler
 * ProjectMap shape that the organization agent's prompt expects.
 *
 * Replaces the deleted analysis-agent.ts which used a separate Gemini call to
 * derive role classifications. The new flow defers role inference to the
 * organization-agent itself; this function just packages the raw state.
 */
function projectStateToMap(state: EnhancedProjectState): ProjectMap {
  return {
    channels: state.channels.map((c) => ({
      index: c.index,
      currentName: c.name,
      pluginName: c.name,
      role: "unknown",
    })),
    summary: `${state.channels.length} channels, ${state.mixer_tracks.length} mixer tracks`,
  };
}

/**
 * Convert a legacy AIPlan (channelAssignments + routingFixes) into the new
 * apply_organization_plan envelope shape.
 */
function aiPlanToBulkPlan(aiPlan: ReturnType<typeof expandPlan>) {
  // expandPlan returns { actions: [...], preview: {...} }
  // Each action is { type, params }. Fold into the bulk-apply shape.
  const channels: Array<{ index: number; name?: string; color?: number; insert?: number }> = [];
  const channelMap = new Map<number, { index: number; name?: string; color?: number; insert?: number }>();

  for (const a of aiPlan.actions) {
    const idx = (a.params as any).index;
    if (typeof idx !== "number") continue;
    const existing = channelMap.get(idx) ?? { index: idx };
    if (a.type === "rename_channel") existing.name = (a.params as any).name;
    else if (a.type === "set_channel_color") existing.color = (a.params as any).color;
    else if (a.type === "set_channel_insert") existing.insert = (a.params as any).insert;
    channelMap.set(idx, existing);
  }
  channels.push(...channelMap.values());
  return { channels };
}

export function organizeTools(userId: string) {
  return {
    apply_organization_plan: relayTool(userId, {
      description: "Apply a structured rename + recolor + (channel only) insert-routing plan in a single FL Studio undo step. Use this for any organize task that touches more than 3 entities — it's one round-trip and one Ctrl+Z to revert. Each section is optional; omit sections you don't need to touch. Item fields are independent (you can pass name, color, or both). The whole apply registers as one undo step. If the response has `undo_grouped: false`, then `undo` must be called with `count: <op_count>` to fully revert.",
      inputSchema: z.object({
        channels: z.array(z.object({
          index: z.number().int().min(0).max(999).describe("0-indexed channel rack entry"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
          insert: z.number().int().min(0).max(126).optional().describe("Target mixer insert"),
        })).optional(),
        mixer_tracks: z.array(z.object({
          index: z.number().int().min(0).max(126).describe("0-indexed mixer track (0=Master, 1-125=Inserts, 126=Current)"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
        playlist_tracks: z.array(z.object({
          index: z.number().int().min(1).max(500).describe("1-indexed playlist track"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
        patterns: z.array(z.object({
          index: z.number().int().min(1).max(999).describe("1-indexed pattern"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
      }),
      toRelay: (plan) => ({ action: "apply_organization_plan", params: plan }),
    }),

    organize_project: tool({
      description: "[Legacy] Analyze and organize the current FL Studio project. Prefer the new flow: call get_project_state, build a plan in chat, then call apply_organization_plan. This tool is retained for backwards compatibility.",
      inputSchema: z.object({
        confirm: z.boolean().default(false).describe("Set to true to apply the plan after previewing."),
      }),
      execute: async (input) => {
        try {
          const stateResult = await relay(userId, "get_project_state", {});
          if (!stateResult.success) {
            return { success: false, error: stateResult.error ?? "Could not read project state" };
          }
          const projectState = stateResult.data as EnhancedProjectState;
          const projectMap = projectStateToMap(projectState);
          const aiPlan = await runOrganization(projectMap, projectState);
          const fullPlan = expandPlan(aiPlan, projectState);
          if (!input.confirm) {
            return {
              success: true,
              status: "preview",
              preview: fullPlan.preview,
              actionCount: fullPlan.actions.length,
            };
          }
          // Apply via the new bulk path instead of action-at-a-time relay calls.
          const bulkPlan = aiPlanToBulkPlan(fullPlan);
          const applyResult = await relay(userId, "apply_organization_plan", bulkPlan);
          if (!applyResult.success) {
            return { success: false, error: applyResult.error };
          }
          const data = applyResult.data as { applied: Record<string, number>; errors: unknown[] };
          return {
            success: data.errors.length === 0,
            status: "applied",
            applied: data.applied,
            errors: data.errors,
          };
        } catch (e) {
          return { success: false, error: e instanceof Error ? e.message : "Organization failed" };
        }
      },
    }),

    scaffold_project: tool({
      description: "Set up a new FL Studio project template based on a genre or style. Renames and color-codes the existing channels in the project to match the genre. Note: FL Studio cannot add channels programmatically, so the template is limited to the number of channels already in the project.",
      inputSchema: z.object({
        genre: z.string().describe("Genre or style description, e.g. 'trap beat', 'lo-fi hip hop', 'dark drill with 808s'"),
        confirm: z.boolean().default(false).describe("Set to true to apply the template after previewing."),
      }),
      execute: async (input) => {
        try {
          const stateResult = await relay(userId, "get_project_state", {});
          if (!stateResult.success) {
            return { success: false, error: "Could not read project state" };
          }
          const projectState = stateResult.data as EnhancedProjectState | undefined;
          if (!projectState?.channels) {
            return { success: false, error: "Project state is empty — open a project with channels in the Channel Rack." };
          }
          const channelCount = projectState.channels.length;

          const aiPlan = await runScaffold(input.genre);
          const trimmedPlan = {
            ...aiPlan,
            channelAssignments: aiPlan.channelAssignments
              .slice(0, channelCount)
              .map((a, i) => ({ ...a, index: projectState.channels[i].index })),
          };
          const fullPlan = expandPlan(trimmedPlan, projectState);

          if (!input.confirm) {
            const skipped = aiPlan.channelAssignments.length - trimmedPlan.channelAssignments.length;
            return {
              success: true,
              status: "preview",
              genre: input.genre,
              preview: fullPlan.preview,
              actionCount: fullPlan.actions.length,
              channelsAvailable: channelCount,
              channelsRequested: aiPlan.channelAssignments.length,
              ...(skipped > 0 && {
                note: `Your project has ${channelCount} channels but the template needs ${aiPlan.channelAssignments.length}. ${skipped} channels were skipped. Add more channels in FL Studio first if you want the full template.`,
              }),
            };
          }
          const bulkPlan = aiPlanToBulkPlan(fullPlan);
          const applyResult = await relay(userId, "apply_organization_plan", bulkPlan);
          if (!applyResult.success) {
            return { success: false, error: applyResult.error };
          }
          const data = applyResult.data as { applied: Record<string, number>; errors: unknown[] };
          return {
            success: data.errors.length === 0,
            status: "applied",
            genre: input.genre,
            applied: data.applied,
            errors: data.errors,
          };
        } catch (e) {
          return { success: false, error: e instanceof Error ? e.message : "Scaffold failed" };
        }
      },
    }),
  };
}
```

- [ ] **Step 2: Verify `analysis-agent.ts` and `execute-plan.ts` have no remaining importers**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai
grep -rn "analysis-agent\|execute-plan" apps/web/src/ || echo "No importers found"
```

Expected: `No importers found` (or only matches inside `analysis-agent.ts`/`execute-plan.ts` themselves).

- [ ] **Step 3: Delete the dead files**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai
rm apps/web/src/lib/ai/organize/analysis-agent.ts
rm apps/web/src/lib/ai/organize/execute-plan.ts
```

- [ ] **Step 4: Type-check + tests**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
bunx tsc --noEmit && bunx vitest run
```

Expected: TS clean. All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/ai/tools/organize.ts apps/web/src/lib/ai/organize/
git commit -m "refactor(ai): legacy organize/scaffold tools route through apply_organization_plan; delete dead analysis-agent.ts and execute-plan.ts"
```

---

## Phase 4 — Manual smoke test

### Task 16: Real FL Studio smoke test (undo grouping decision)

Per spec §5.3 and §9.4: the most uncertain piece is whether `general.saveUndo` actually groups setter calls into a single undo step at runtime. Bridge unit tests prove the call ordering is correct, but FL Studio's behavior under high-frequency setter loops can only be verified on the real DAW.

**No file changes in this task** — it's a verification gate. If undo grouping fails, we already shipped the `op_count` + `undo({count})` fallback in Tasks 2 and 13, so the AI-side workflow stays intact.

- [ ] **Step 1: Bring up the full stack**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai
./dev.sh
```

Open FL Studio and load the Studio AI plugin. Confirm the bridge connects (`[Studio AI] Pipe transport connected (lazy)` appears in FL Studio's Script log).

- [ ] **Step 2: Set up a test project**

In FL Studio:
- Create or open a project with **at least 50 channels** (drum samples, synths — any mix).
- Add **at least 30 mixer tracks** with default names ("Insert 1" … "Insert 30").
- Add **at least 10 playlist tracks**.

Save the project as `studio-ai-smoke.flp` so you can reload it between runs.

- [ ] **Step 3: Trigger an organize via the plugin**

In the plugin chat:
```
Organize this project. Group drums, bass, leads, and FX. Color-code by group.
```

Wait for the AI to:
1. Call `get_project_state`
2. Output a textual plan
3. Call `save_project` (checkpoint)
4. Call `apply_organization_plan`
5. Confirm completion

Verify visually in FL Studio that channels and mixer tracks are renamed and colored.

- [ ] **Step 4: Verify single-undo grouping**

In FL Studio: press **Ctrl+Z** (Cmd+Z on macOS) **once**.

Expected (success): the **entire batch** reverts — every name and color goes back to its pre-apply state in one undo.

If only one or two items revert per Ctrl+Z, undo grouping failed. **Move to Step 5.** Otherwise, skip to Step 6.

- [ ] **Step 5: (Conditional) Verify the count fallback**

The bridge already returns `undo_grouped: false` and `op_count: N` in the apply response when grouping fails. In the plugin chat:
```
That undo only reverted one thing. Undo the rest.
```

Expected: AI calls `undo` with `count: <op_count>`. All remaining items revert.

If the model doesn't pick up the count automatically, file a follow-up to update the system prompt to be more explicit (e.g. "When a recent apply_organization_plan returned undo_grouped:false, ALWAYS pass count when the user asks to undo it").

- [ ] **Step 6: Verify the find-by-name flow**

Reload `studio-ai-smoke.flp`. In the plugin chat:
```
Color the kick red.
```

Expected:
1. AI calls `find_channel_by_name` with `query: "kick"`.
2. AI shows the matched channel(s).
3. If unambiguous, AI calls `set_channel_color` with the resolved index and `color: 0xFF0000`.
4. If ambiguous, AI asks "I see Kick (3) and Kick Layer (7) — which one?"

- [ ] **Step 7: Verify the PLAN_TOO_LARGE guard**

In the plugin chat (or via direct curl to `/api/ai/execute`):
```
Rename channels 0 through 2500, name them ch_0, ch_1, etc.
```

Expected: AI either chunks the work into ≤2000-item batches automatically, or `apply_organization_plan` returns `error: "PLAN_TOO_LARGE"` and the AI tells the user it needs to split.

- [ ] **Step 8: Document outcomes**

Open the spec at `docs/superpowers/specs/2026-04-15-organize-bulk-and-tool-registry-design.md`. Add a new section at the end:

```markdown
## 13. Smoke Test Results (YYYY-MM-DD)

- FL Studio version tested: <e.g. 21.2 macOS>
- Plugin build SHA: <git rev-parse HEAD>
- Test project: 50 channels, 30 mixer tracks, 10 playlist tracks
- Single-undo grouping: ✅ works / ❌ fell back to op_count loop
- find-by-name flow: ✅ resolved correctly / ⚠ ambiguity prompt fired as expected
- PLAN_TOO_LARGE guard: ✅ AI chunked / ⚠ surfaced error to user
- Other observations: <free text>
```

- [ ] **Step 9: Commit smoke test results**

```bash
git add docs/superpowers/specs/2026-04-15-organize-bulk-and-tool-registry-design.md
git commit -m "docs(ai): record smoke-test results for organize bulk-apply spec"
```

- [ ] **Step 10: Stop the dev stack**

In the dev.sh terminal: Ctrl+C.

---

## Self-Review Notes

The plan covers every section of the spec:

| Spec section | Implementing task(s) |
|---|---|
| §3 Six new commands | Tasks 2 (apply), 3 (undo, save), 4 (find_*) |
| §4.1 apply_organization_plan contract | Tasks 2 (handler) + 13 step 8 (TS tool) |
| §4.2 undo + save_project contracts | Tasks 3 (handlers) + 13 step 3 (TS tools) |
| §4.3 find-by-name contracts + scoring | Tasks 4 (handler + scoring) + 13 steps 4/5/6 |
| §5.1 handlers_bulk.py file | Tasks 2/3/4 (incremental) |
| §5.2 device_studio_ai.py wiring | Task 5 |
| §5.3 saveUndo fallback | Task 2 step 3 (hasattr + try/except) + Task 16 |
| §6.1 Folder structure | Tasks 7-11 |
| §6.2 _shared.ts helper | Task 7 |
| §6.3-6.5 domain modules + route.ts | Tasks 8-12 |
| §7.1 Organize flow refactor | Tasks 14 (prompt) + 15 (legacy tool rewire) |
| §8 Error handling | Covered by handler-level tests in Tasks 2/4 + relayTool tests in Task 7 |
| §9 Testing | Tasks 1-4 (bridge), Tasks 7/11 (TS), Task 16 (manual) |
| §10 Implementation order | Phases 1-4 mirror spec's order exactly |
| §11 Open risks | Task 16 verifies the largest one (undo grouping) |
| §12 Vault docs | Out of plan scope per spec; happens after merge via vault-maintain skill |
