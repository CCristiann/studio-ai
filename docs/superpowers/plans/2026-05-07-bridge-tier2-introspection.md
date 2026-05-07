# Bridge Tier 2 Introspection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the FL Studio bridge enough read-only structural introspection (plugin identity, mixer routing graph, send levels, effect chains, EQ values, pattern length, selection state, FL capabilities) for the AI agent to organize messy projects intelligently.

**Architecture:** New `bridge/fl_studio/handlers_introspect.py` module exporting `INTROSPECT_HANDLERS`, registered in `device_studio_ai.py` alongside `ORGANIZE_HANDLERS` and `BULK_HANDLERS`. Capability probe gates every version-dependent FL API call. Web tool registry gains four new domain tools and one schema extension. TypeScript types migrate the `channels[].plugin` shape from `string` to `{name, type, type_label} | null`, with an adapter in `_shared.ts:projectStateToMap` preserving the existing string contract for the legacy organize agent.

**Tech Stack:** Python (FL embedded sandbox; pytest+unittest for bridge tests), TypeScript (Next.js 16; vitest for web tests), Zod schemas, Vercel AI SDK 5 (`tool()` + `streamText`), Bun (TS toolchain).

**Spec:** [docs/superpowers/specs/2026-05-07-bridge-tier2-introspection-design.md](../specs/2026-05-07-bridge-tier2-introspection-design.md) — read §1 (FL version floor), §4 (commands), §6 (perf budget), §13 (TS migration) before starting.

---

## File Structure

### Created

- `bridge/fl_studio/handlers_introspect.py` — capability probe + 5 new READ handlers
- `bridge/fl_studio/tests/test_handlers_introspect.py` — pytest suite for the above
- `apps/web/src/lib/ai/organize/__tests__/projectStateToMap.test.ts` — adapter unit test (new directory if absent)

### Modified

- `bridge/fl_studio/tests/conftest.py` — extend FL mocks with new functions (plugins module, mixer routing/EQ/slot-color, channels.getChannelType/selectedChannel, patterns.getPatternLength/patternNumber, mixer.trackNumber, ui.getVersion, general.getVersion)
- `bridge/fl_studio/device_studio_ai.py` — register `INTROSPECT_HANDLERS`
- `packages/types/src/organize.ts` — `ChannelInfo.plugin` shape change + new `ChannelTypeLabel`, extend `MixerTrackInfo` with `slot_count` + `routes_to`, extend `PatternInfo` with `length_beats?`, extend `EnhancedProjectState` with `selection`/`capabilities`/`snapshot_at`/`truncated_sections?`
- `apps/web/src/lib/ai/organize/types.ts` — Zod `plugin` schema change
- `apps/web/src/lib/ai/organize/_shared.ts` — adapter formats `c.plugin` as `"Sytrus (vst)"`
- `apps/web/src/lib/ai/tools/project.ts` — `get_project_state` gains `include_routing` param
- `apps/web/src/lib/ai/tools/mixer.ts` — add `get_mixer_chain`, `get_mixer_plugin_params`, `get_mixer_eq`
- `apps/web/src/lib/ai/tools/channels.ts` — add `get_channel_plugin_params`
- `apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts` — snapshot update + `include_routing` schema assertion
- `apps/web/src/lib/ai/system-prompt.ts` — append "Reading project context" + worked examples + anti-refetch rule

### Untouched (intentional)

- All `apps/web/src/lib/ai/organize/*.ts` files except `types.ts` and `_shared.ts` — the adapter strategy preserves the legacy organize agent's string contract internally.
- `bridge/fl_studio/handlers_organize.py` — the existing `_cmd_get_project_state` is kept as fallback under the older `get_state` alias; the new handler from this plan overrides the `get_project_state` registration via dict-merge order in `device_studio_ai.py`.

---

## Phase 1 — Foundation: test infrastructure + TypeScript migration

These tasks land first and can be merged independently. They unblock everything downstream.

### Task 1: Extend conftest.py with new FL mock surface

**Files:**
- Modify: `bridge/fl_studio/tests/conftest.py`

**Why:** Tests in Phase 2+ need mocks for `plugins.*`, `mixer.getRouteSendActive`, `mixer.getRouteToLevel`, `mixer.getEqGain/Frequency/Bandwidth`, `mixer.getSlotColor`, `mixer.isTrackSlotsEnabled`, `mixer.trackNumber`, `channels.getChannelType`, `channels.selectedChannel`, `patterns.getPatternLength`, `patterns.patternNumber`, `general.getVersion`, plus a `ui` mock module.

- [ ] **Step 1: Read the current conftest.py end-to-end** so the additions match its style.

```bash
cat bridge/fl_studio/tests/conftest.py
```

- [ ] **Step 2: Append `_make_plugins_mock` factory.**

Edit `bridge/fl_studio/tests/conftest.py`. Insert this function before `install_fl_mocks`:

```python
def _make_plugins_mock():
    """Mock for FL's `plugins` module: tracks per-(target, slot) state.

    Address conventions (matching real FL):
      - Mixer slot plugin: target = mixer track index, slot in 0..9
      - Channel rack plugin: target = channel index, slot = -1
    `valid` defaults to {}, so isValid returns False unless explicitly set.
    """
    mod = types.ModuleType("plugins")
    mod.valid = {}        # {(target, slot): bool}
    mod.names = {}        # {(target, slot): str}
    mod.param_counts = {} # {(target, slot): int}
    mod.param_names = {}  # {(target, slot, param_idx): str}
    mod.param_values = {} # {(target, slot, param_idx): float}
    mod.param_value_strings = {}  # {(target, slot, param_idx): str}
    mod._raise_on_param = set()   # {(target, slot, param_idx)}
    mod._sleep_per_param_s = 0.0  # for time-budget tests
    mod.calls = []

    def isValid(target, slot, useGlobalIndex=False):
        return bool(mod.valid.get((target, slot), False))

    def getPluginName(target, slot, useGlobalIndex=False):
        return mod.names.get((target, slot), "")

    def getParamCount(target, slot, useGlobalIndex=False):
        return int(mod.param_counts.get((target, slot), 0))

    def getParamName(param_idx, target, slot, useGlobalIndex=False):
        if (target, slot, param_idx) in mod._raise_on_param:
            raise RuntimeError("simulated FL param error")
        return mod.param_names.get((target, slot, param_idx), "")

    def getParamValue(param_idx, target, slot, useGlobalIndex=False):
        if mod._sleep_per_param_s:
            import time as _time
            _time.sleep(mod._sleep_per_param_s)
        return float(mod.param_values.get((target, slot, param_idx), 0.0))

    def getParamValueString(param_idx, target, slot, useGlobalIndex=False):
        return mod.param_value_strings.get((target, slot, param_idx), "")

    mod.isValid = isValid
    mod.getPluginName = getPluginName
    mod.getParamCount = getParamCount
    mod.getParamName = getParamName
    mod.getParamValue = getParamValue
    mod.getParamValueString = getParamValueString
    return mod
```

- [ ] **Step 3: Extend `_make_mixer_mock` with routing, EQ, slot color, slots-enabled, trackNumber.**

Inside `_make_mixer_mock`, after the existing fields and before the `def trackCount` block, add:

```python
    mod.routes = {}           # {(src, dst): bool}
    mod.route_levels = {}     # {(src, dst): float}
    mod.eq = {}               # {(track, band): {"gain": f, "freq": f, "bw": f}}
    mod.slot_colors = {}      # {(track, slot): int}
    mod.slots_enabled = {}    # {track: bool}
    mod._selected_track = 0
```

Inside the same factory, before the closing `mod.* = ...` block at the end, add the new functions:

```python
    def getRouteSendActive(src, dst):
        return bool(mod.routes.get((src, dst), False))

    def getRouteToLevel(src, dst):
        return float(mod.route_levels.get((src, dst), 0.8))

    def getEqGain(track, band):
        return float(mod.eq.get((track, band), {"gain": 0.5}).get("gain", 0.5))

    def getEqFrequency(track, band):
        return float(mod.eq.get((track, band), {"freq": 0.5}).get("freq", 0.5))

    def getEqBandwidth(track, band):
        return float(mod.eq.get((track, band), {"bw": 0.5}).get("bw", 0.5))

    def getSlotColor(track, slot):
        return int(mod.slot_colors.get((track, slot), 0))

    def isTrackSlotsEnabled(track):
        return bool(mod.slots_enabled.get(track, True))

    def trackNumber():
        return int(mod._selected_track)
```

And at the end of the factory, after the existing `mod.setTrackEQBW = setTrackEQBW` line, add:

```python
    mod.getRouteSendActive   = getRouteSendActive
    mod.getRouteToLevel      = getRouteToLevel
    mod.getEqGain            = getEqGain
    mod.getEqFrequency       = getEqFrequency
    mod.getEqBandwidth       = getEqBandwidth
    mod.getSlotColor         = getSlotColor
    mod.isTrackSlotsEnabled  = isTrackSlotsEnabled
    mod.trackNumber          = trackNumber
```

- [ ] **Step 4: Extend `_make_channels_mock` with `getChannelType`, `selectedChannel`.**

Inside `_make_channels_mock`, add to the state fields:

```python
    mod.types = {}              # {index: int channel-type code}
    mod._selected_channel = 0
```

Add the functions:

```python
    def getChannelType(i):
        return int(mod.types.get(i, 2))   # default to "vst"

    def selectedChannel():
        return int(mod._selected_channel)
```

And register them at the end of the factory:

```python
    mod.getChannelType  = getChannelType
    mod.selectedChannel = selectedChannel
```

- [ ] **Step 5: Extend `_make_patterns_mock` with `getPatternLength`, `patternNumber`.**

```python
    mod.lengths = {}           # {index: int beats}
    mod._selected_pattern = 1
```

```python
    def getPatternLength(i):
        return int(mod.lengths.get(i, 0))

    def patternNumber():
        return int(mod._selected_pattern)
```

```python
    mod.getPatternLength = getPatternLength
    mod.patternNumber    = patternNumber
```

- [ ] **Step 6: Extend `_make_general_mock` with `getVersion`.**

```python
    mod._api_version = 36   # FL 2024 default for tests
```

```python
    def getVersion():
        return int(mod._api_version)
```

```python
    mod.getVersion = getVersion
```

- [ ] **Step 7: Add `_make_ui_mock` factory.**

Add a new factory before `install_fl_mocks`:

```python
def _make_ui_mock():
    mod = types.ModuleType("ui")
    mod._fl_version_tuple = (21, 2, 3, 4321)

    def getVersion(mode=0):
        return tuple(mod._fl_version_tuple)

    mod.getVersion = getVersion
    return mod
```

- [ ] **Step 8: Wire the new mocks into `install_fl_mocks` and `uninstall_fl_mocks`.**

Update `install_fl_mocks`:

```python
def install_fl_mocks():
    mocks = {
        "general":  _make_general_mock(),
        "channels": _make_channels_mock(),
        "mixer":    _make_mixer_mock(),
        "playlist": _make_playlist_mock(),
        "patterns": _make_patterns_mock(),
        "plugins":  _make_plugins_mock(),
        "ui":       _make_ui_mock(),
    }
    for name, mod in mocks.items():
        sys.modules[name] = mod
    midi_mod = types.ModuleType("midi")
    midi_mod.REC_MainPitch     = 0
    midi_mod.REC_Tempo         = 1
    midi_mod.REC_Control       = 2
    midi_mod.REC_UpdateControl = 4
    sys.modules["midi"] = midi_mod
    sys.modules["transport"] = types.ModuleType("transport")
    sys.modules["transport"].isPlaying = lambda: False
    return mocks
```

Update `uninstall_fl_mocks`:

```python
def uninstall_fl_mocks():
    for name in ("general", "channels", "mixer", "playlist", "patterns",
                 "plugins", "ui", "midi", "transport"):
        sys.modules.pop(name, None)
```

- [ ] **Step 9: Run the existing test suite to ensure conftest changes don't break anything.**

Run: `cd bridge/fl_studio && python -m pytest tests/ -q`
Expected: all existing tests pass (28 of 28 from prior smoke results).

- [ ] **Step 10: Commit.**

```bash
git add bridge/fl_studio/tests/conftest.py
git commit -m "$(cat <<'EOF'
test(bridge): extend FL mocks for tier 2 introspection surface

Adds plugins module mock + new mixer/channels/patterns/general/ui
functions (routing, EQ, slot color, getChannelType, getPatternLength,
selectedChannel/patternNumber/trackNumber, getVersion). Foundation
for handlers_introspect.py tests in next tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Update TypeScript types in `packages/types`

**Files:**
- Modify: `packages/types/src/organize.ts`

**Why:** Bridge response shape change for `channels[].plugin` (string → object). Adds `MixerTrackInfo.slot_count`/`routes_to`, `PatternInfo.length_beats?`, `EnhancedProjectState.selection`/`capabilities`/`snapshot_at`/`truncated_sections?`. See spec §13.1.

- [ ] **Step 1: Read current types file.**

```bash
cat packages/types/src/organize.ts
```

- [ ] **Step 2: Add `ChannelTypeLabel` type and update `ChannelInfo`.**

Replace the `// ── Enhanced Project State (returned by get_project_state) ──` block (currently lines 74–115). The full replacement:

```typescript
// ── Enhanced Project State (returned by get_project_state) ──

export type ChannelTypeLabel =
  | "sampler"
  | "hybrid"
  | "vst"
  | "automation"
  | "layer"
  | "midi_out"
  | "unknown";

export interface ChannelPluginInfo {
  name: string;
  type: number;
  type_label: ChannelTypeLabel;
}

export interface ChannelInfo {
  index: number;
  name: string;
  /**
   * Plugin identity. `null` only when channels.getChannelType raised in the
   * bridge (rare). For sampler channels with no instrument loaded, expect
   * `{ name: "", type: 0, type_label: "sampler" }`.
   */
  plugin: ChannelPluginInfo | null;
  color: number;
  volume: number;
  pan: number;
  enabled: boolean;
  insert: number;
}

export interface MixerRoute {
  to_index: number;
  /** Send level 0..1, omitted on FL <2024 (capabilities.has_send_levels === false). */
  level?: number;
}

export interface MixerTrackInfo {
  index: number;
  name: string;
  color: number;
  volume: number;
  pan: number;
  muted: boolean;
  /** # of loaded effect slots (0..10). */
  slot_count: number;
  /** Outbound routing graph. Empty array means only the implicit Master route. */
  routes_to: MixerRoute[];
}

export interface PlaylistTrackInfo {
  index: number;
  name: string;
  color: number;
}

export interface PatternInfo {
  index: number;
  name: string;
  color: number;
  /** Pattern length in beats. Omitted when capabilities.has_pattern_length is false. */
  length_beats?: number;
}

export interface ProjectSelection {
  channel_index: number | null;
  pattern_index: number | null;
  mixer_track_index: number | null;
}

export interface ProjectCapabilities {
  fl_version: string;
  api_version: number;
  has_send_levels: boolean;
  has_eq_getters: boolean;
  has_save_undo: boolean;
  has_pattern_length: boolean;
  has_slot_color: boolean;
}

export type TruncatedSection =
  | "channels"
  | "mixer_tracks"
  | "patterns"
  | "playlist_tracks"
  | "routing";

export interface EnhancedProjectState {
  bpm: number;
  project_name: string;
  playing: boolean;
  channels: ChannelInfo[];
  mixer_tracks: MixerTrackInfo[];
  playlist_tracks: PlaylistTrackInfo[];
  patterns: PatternInfo[];
  selection: ProjectSelection;
  capabilities: ProjectCapabilities;
  snapshot_at: number;
  /** Present only when caps fired during enumeration. */
  truncated_sections?: TruncatedSection[];
  /** When `truncated_sections` includes "routing", index of the last track that was swept. */
  routing_swept_through?: number;
}
```

- [ ] **Step 3: Run tsc to verify no compile errors in the package itself.**

```bash
cd packages/types && bunx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Run tsc across the web app to surface downstream breakage.**

```bash
cd apps/web && bunx tsc --noEmit
```
Expected: errors in `apps/web/src/lib/ai/organize/_shared.ts` (because `c.plugin` is now an object). That's expected — Task 4 fixes it.

- [ ] **Step 5: Commit.**

```bash
git add packages/types/src/organize.ts
git commit -m "$(cat <<'EOF'
types(organize): tier 2 introspection shape change

ChannelInfo.plugin: string → ChannelPluginInfo | null
MixerTrackInfo gains slot_count + routes_to
PatternInfo gains length_beats?
EnhancedProjectState gains selection / capabilities /
  snapshot_at / truncated_sections?

Downstream organize agent code adapts via _shared.ts in
the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Update Zod schema in `apps/web/src/lib/ai/organize/types.ts`

**Files:**
- Modify: `apps/web/src/lib/ai/organize/types.ts:11`

**Why:** The Zod schema for `projectMapSchema.channels[].plugin` declares `z.string()`. The bridge now sends an object, so the parse will fail unless we update the schema. But — `projectStateToMap` (Task 4) collapses the object into a string before this schema sees it, so we keep the Zod as `z.string()`. **No change needed in this file.** Confirm and skip.

- [ ] **Step 1: Re-read the file.**

```bash
cat apps/web/src/lib/ai/organize/types.ts
```

- [ ] **Step 2: Confirm `projectMapSchema` validates the OUTPUT of `projectStateToMap`, not the bridge response.**

Search for callers of `projectMapSchema`:

```bash
grep -rn "projectMapSchema" apps/web/src/ 2>/dev/null
```

Expected: only used inside `apps/web/src/lib/ai/organize/`, downstream of `projectStateToMap`. The bridge response is never directly Zod-parsed against this schema.

- [ ] **Step 3: No file edit. Move on.**

If the search reveals a direct bridge-to-Zod path (unlikely), add a `ChannelPluginInfo`-shaped variant; otherwise this task is documentation-only.

- [ ] **Step 4: No commit (no change).** Skip to Task 4.

---

### Task 4: Adapter + unit test for `projectStateToMap`

**Files:**
- Modify: `apps/web/src/lib/ai/organize/_shared.ts:32`
- Create: `apps/web/src/lib/ai/organize/__tests__/projectStateToMap.test.ts`

**Why:** Adapter formats `channels[].plugin` as `"Sytrus (vst)"` to preserve role-inference signal that the legacy organize agent's prompt depends on. See spec §13.1.

- [ ] **Step 1: Create the test file (write the failing test first).**

```bash
mkdir -p apps/web/src/lib/ai/organize/__tests__
```

`apps/web/src/lib/ai/organize/__tests__/projectStateToMap.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { projectStateToMap } from "../_shared";
import type { EnhancedProjectState } from "@studio-ai/types";

const baseState = (): EnhancedProjectState => ({
  bpm: 128,
  project_name: "Test",
  playing: false,
  channels: [],
  mixer_tracks: [],
  playlist_tracks: [],
  patterns: [],
  selection: { channel_index: null, pattern_index: null, mixer_track_index: null },
  capabilities: {
    fl_version: "21.2.3",
    api_version: 36,
    has_send_levels: true,
    has_eq_getters: true,
    has_save_undo: true,
    has_pattern_length: true,
    has_slot_color: true,
  },
  snapshot_at: 0,
});

describe("projectStateToMap", () => {
  it("formats plugin as 'name (type_label)' for VST channels", () => {
    const state = baseState();
    state.channels = [{
      index: 0, name: "Lead", color: 0, volume: 0.78, pan: 0, enabled: true, insert: 1,
      plugin: { name: "Sytrus", type: 2, type_label: "vst" },
    }];
    const map = projectStateToMap(state);
    expect(map.channels[0].plugin).toBe("Sytrus (vst)");
  });

  it("formats plugin as 'name (sampler)' for sampler channels", () => {
    const state = baseState();
    state.channels = [{
      index: 0, name: "Kick", color: 0, volume: 0.78, pan: 0, enabled: true, insert: 1,
      plugin: { name: "Sampler", type: 0, type_label: "sampler" },
    }];
    const map = projectStateToMap(state);
    expect(map.channels[0].plugin).toBe("Sampler (sampler)");
  });

  it("returns '(unknown)' when plugin is null", () => {
    const state = baseState();
    state.channels = [{
      index: 0, name: "Mystery", color: 0, volume: 0.78, pan: 0, enabled: true, insert: 1,
      plugin: null,
    }];
    const map = projectStateToMap(state);
    expect(map.channels[0].plugin).toBe("(unknown)");
  });

  it("preserves all other channel fields verbatim", () => {
    const state = baseState();
    state.channels = [{
      index: 7, name: "Bass", color: 0xFF0000, volume: 0.6, pan: -0.2, enabled: true, insert: 9,
      plugin: { name: "FLEX", type: 2, type_label: "vst" },
    }];
    const map = projectStateToMap(state);
    expect(map.channels[0].index).toBe(7);
    expect(map.channels[0].currentName).toBe("Bass");
    expect(map.channels[0].plugin).toBe("FLEX (vst)");
    expect(map.channels[0].inferredRole).toBe("unknown");
    expect(map.channels[0].roleGroup).toBe("other");
    expect(map.channels[0].confidence).toBe("low");
  });
});
```

- [ ] **Step 2: Run the test — confirm it fails.**

```bash
cd apps/web && bunx vitest run src/lib/ai/organize/__tests__/projectStateToMap.test.ts
```
Expected: 4 failures because `projectStateToMap` currently does `plugin: c.plugin` (which is now an object, not a string).

- [ ] **Step 3: Update `_shared.ts:32`.**

Open `apps/web/src/lib/ai/organize/_shared.ts`, replace the line `plugin: c.plugin,` with:

```typescript
      plugin: c.plugin ? `${c.plugin.name} (${c.plugin.type_label})` : "(unknown)",
```

- [ ] **Step 4: Run the test again.**

```bash
cd apps/web && bunx vitest run src/lib/ai/organize/__tests__/projectStateToMap.test.ts
```
Expected: 4/4 passing.

- [ ] **Step 5: Run `tsc --noEmit` to confirm no remaining type errors.**

```bash
cd apps/web && bunx tsc --noEmit
```
Expected: clean.

- [ ] **Step 6: Run the full web test suite to catch any regressions.**

```bash
cd apps/web && bun run test
```
Expected: all green.

- [ ] **Step 7: Commit.**

```bash
git add apps/web/src/lib/ai/organize/_shared.ts apps/web/src/lib/ai/organize/__tests__/projectStateToMap.test.ts
git commit -m "$(cat <<'EOF'
fix(web): adapt projectStateToMap to ChannelPluginInfo shape

Bridge now returns plugin as { name, type, type_label } object;
adapter collapses it to "name (type_label)" string so the legacy
organize agent's prompt sees richer info than just the raw name.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Bridge introspection module

### Task 5: Create `handlers_introspect.py` skeleton + capability probe + tests

**Files:**
- Create: `bridge/fl_studio/handlers_introspect.py`
- Create: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** Capability probe is the foundation every other handler gates on. See spec §5.

- [ ] **Step 1: Write the failing tests.**

`bridge/fl_studio/tests/test_handlers_introspect.py`:

```python
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
```

- [ ] **Step 2: Run the tests — confirm they fail because the module doesn't exist.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py -v
```
Expected: ImportError or "No module named handlers_introspect".

- [ ] **Step 3: Create the module skeleton with the capability probe.**

`bridge/fl_studio/handlers_introspect.py`:

```python
# bridge/fl_studio/handlers_introspect.py
"""FL Studio bridge — Tier 2 read-only project introspection.

Imported by device_studio_ai.py via:
    from handlers_introspect import INTROSPECT_HANDLERS

Capability detection (§5 of the design spec) gates every version-dependent
FL function. Permissive defaults survive cold-start race where FL modules
have not yet been populated.
"""
import time

# Module-level capability cache. None = unprobed; api_version=0 = probe failed
# (re-probe on next call); api_version>0 = good cache.
_CAPS = None

# Channel-type label map. Codes are stable across FL versions.
_CHANNEL_TYPE_LABELS = {
    0: "sampler",
    1: "hybrid",
    2: "vst",
    3: "midi_out",
    4: "automation",
    5: "layer",
}


def _probe_capabilities():
    """Probe FL Studio module surface once. Returns cached result on
    subsequent calls. On any failure, returns permissive defaults rather
    than raising — the bridge stays up and the agent sees an honest
    'minimal capabilities' view.
    """
    global _CAPS
    if _CAPS is not None and _CAPS.get("api_version", 0) > 0:
        return _CAPS

    fl_version = "unknown"
    api_version = 0
    has = {
        # Floor core (FL 20.7+, API ≥ 19)
        "channels.getChannelType":    False,
        "plugins.getPluginName":      False,
        "plugins.isValid":            False,
        "mixer.getRouteSendActive":   False,
        "channels.selectedChannel":   False,
        "patterns.patternNumber":     False,
        "mixer.trackNumber":          False,
        # FL 2024+ additions
        "mixer.getRouteToLevel":      False,
        "mixer.getEqGain":            False,
        "mixer.getSlotColor":         False,
        # Other gating
        "general.saveUndo":           False,
        "patterns.getPatternLength":  False,
        "ui.getVersion":              False,
    }
    try:
        import channels
        import mixer
        import patterns
        import plugins
        import general
        import ui
        mods = {"channels": channels, "mixer": mixer, "patterns": patterns,
                "plugins": plugins, "general": general, "ui": ui}
        for key in has:
            mod_name, fn_name = key.split(".")
            has[key] = hasattr(mods[mod_name], fn_name)
        try:
            api_version = int(general.getVersion())
        except Exception:
            api_version = 0
        try:
            ver_tuple = ui.getVersion(0) if has["ui.getVersion"] else None
            if isinstance(ver_tuple, (list, tuple)):
                fl_version = ".".join(str(x) for x in ver_tuple)
            else:
                fl_version = str(ver_tuple) if ver_tuple else "unknown"
        except Exception:
            pass
    except Exception:
        # Permissive defaults; everything stays False.
        pass

    _CAPS = {
        "fl_version":         fl_version,
        "api_version":        api_version,
        "has_send_levels":    has["mixer.getRouteToLevel"],
        "has_eq_getters":     has["mixer.getEqGain"],
        "has_save_undo":      has["general.saveUndo"],
        "has_pattern_length": has["patterns.getPatternLength"],
        "has_slot_color":     has["mixer.getSlotColor"],
        "_has_floor_core":    all(has[k] for k in (
            "channels.getChannelType", "plugins.getPluginName",
            "plugins.isValid", "mixer.getRouteSendActive",
            "channels.selectedChannel", "patterns.patternNumber",
            "mixer.trackNumber",
        )),
    }
    return _CAPS


def _cmd_get_capabilities(_params):
    """Internal probe handler. Not exposed as an AI tool — see §4.5 of spec."""
    return _probe_capabilities()


# Handler registry — populated as later tasks add commands.
INTROSPECT_HANDLERS = {
    # Note: get_project_state is NOT yet registered here. Task 9 adds it.
    # The capabilities probe is internal-only (not in the registry).
}
```

- [ ] **Step 4: Run the tests again — confirm they pass.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py -v
```
Expected: 6/6 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): handlers_introspect with capability probe

Foundation for tier 2 read-only introspection. Probes FL module
surface once (with re-probe on cold-start failure), gates every
version-dependent call. Permissive defaults survive cold start.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add `_channel_plugin` helper + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** Returns `{name, type, type_label}` for a single channel. Used by the extended `get_project_state` handler in Task 9.

- [ ] **Step 1: Write failing tests.** Append to `tests/test_handlers_introspect.py`:

```python
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
```

- [ ] **Step 2: Run — expect import errors for `_channel_plugin`.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::ChannelPluginTests -v
```
Expected: 5 failures (`AttributeError: module 'handlers_introspect' has no attribute '_channel_plugin'`).

- [ ] **Step 3: Add the helper.** In `handlers_introspect.py`, after `_cmd_get_capabilities`:

```python
def _channel_plugin(idx):
    """Return {name, type, type_label} for a channel, or None on error."""
    import channels
    import plugins
    try:
        type_code = int(channels.getChannelType(idx))
    except Exception:
        return None
    try:
        plugin_name = plugins.getPluginName(idx, -1) or ""
    except Exception:
        plugin_name = ""
    return {
        "name":       plugin_name,
        "type":       type_code,
        "type_label": _CHANNEL_TYPE_LABELS.get(type_code, "unknown"),
    }
```

- [ ] **Step 4: Run — expect pass.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::ChannelPluginTests -v
```
Expected: 5/5 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): _channel_plugin helper for plugin identity reads

Returns { name, type, type_label } for a channel rack entry. Used by
extended get_project_state in next tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add `_mixer_routes` helper + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** Returns the outbound routing graph for a single mixer track. Includes send levels on FL 2024+. Used by extended `get_project_state` (Task 9). See spec §7.1.

- [ ] **Step 1: Write failing tests.** Append:

```python
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
```

- [ ] **Step 2: Run — expect 5 failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::MixerRoutesTests -v
```

- [ ] **Step 3: Add the helper.** In `handlers_introspect.py`, after `_channel_plugin`:

```python
def _mixer_routes(src):
    """Return list of {to_index, level?} for outbound sends from src.

    Excludes self-route. Level is included only when caps.has_send_levels
    is true. Per-call exceptions are caught so a single bad pair doesn't
    abort the sweep.
    """
    import mixer
    caps = _probe_capabilities()
    sends = []
    track_count = mixer.trackCount()
    for dst in range(track_count):
        if dst == src:
            continue
        try:
            if not bool(mixer.getRouteSendActive(src, dst)):
                continue
        except Exception:
            continue
        entry = {"to_index": dst}
        if caps["has_send_levels"]:
            try:
                entry["level"] = round(float(mixer.getRouteToLevel(src, dst)), 3)
            except Exception:
                pass
        sends.append(entry)
    return sends
```

- [ ] **Step 4: Run — expect pass.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::MixerRoutesTests -v
```
Expected: 5/5 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): _mixer_routes helper for routing graph reads

Returns outbound sends for a track, with levels when FL 2024+
capability is present. Self-route skipped, per-pair exceptions
tolerated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Add `_mixer_slot_count` and `_selection` helpers + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** Two small helpers used by extended `get_project_state`. Slot count is cheap-to-call (10 isValid per track). Selection state is non-transactional (caveat documented in spec §4.1).

- [ ] **Step 1: Write failing tests.** Append:

```python
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
```

- [ ] **Step 2: Run — expect 5 failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::SmallHelperTests -v
```

- [ ] **Step 3: Add helpers.** In `handlers_introspect.py`, after `_mixer_routes`:

```python
def _mixer_slot_count(track):
    """Return # of loaded effect slots on `track` (0..10).

    Uses `continue` (not `break`) on per-slot exceptions: a single
    misbehaving slot must not silently undercount the rest of the chain.
    """
    import plugins
    n = 0
    for slot in range(10):
        try:
            if bool(plugins.isValid(track, slot)):
                n += 1
        except Exception:
            continue
    return n


def _selection():
    """Return current selection state. Reads three FL functions sequentially
    without locking; per-field exceptions degrade individual fields to None.
    NOT a transactional snapshot — see spec §4.1 caveat.
    """
    import channels
    import patterns
    import mixer
    sel = {"channel_index": None, "pattern_index": None, "mixer_track_index": None}
    try:
        sel["channel_index"] = int(channels.selectedChannel())
    except Exception:
        pass
    try:
        sel["pattern_index"] = int(patterns.patternNumber())
    except Exception:
        pass
    try:
        sel["mixer_track_index"] = int(mixer.trackNumber())
    except Exception:
        pass
    return sel
```

- [ ] **Step 4: Run — expect pass.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::SmallHelperTests -v
```
Expected: 5/5 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): _mixer_slot_count and _selection helpers

Slot count uses continue (not break) on per-slot exceptions to avoid
silent undercount. Selection state is non-transactional; per-field
exceptions degrade to None per spec §4.1 caveat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Implement extended `_cmd_get_project_state` (without truncation envelope) + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** This is the load-bearing handler. Implements the response shape from spec §4.1 minus the `include_routing` flag and truncation caps (Task 10 adds those). See spec §7.

- [ ] **Step 1: Write failing tests.** Append:

```python
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
```

- [ ] **Step 2: Run — expect failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::GetProjectStateTests -v
```

- [ ] **Step 3: Implement the handler.** In `handlers_introspect.py`, after `_selection`:

```python
# ────────────────────────────────────────────────────────────────────
# get_project_state — extended with plugin identity, routing, slot
# counts, pattern length, selection, capabilities.
# ────────────────────────────────────────────────────────────────────

def _is_default_mixer_name(name, idx):
    if not name:
        return True
    if idx == 0 and name == "Master":
        return False
    return name.startswith("Insert ") or name == "Current"


def _is_default_playlist_name(name):
    return not name or name.startswith("Track ")


def _is_default_pattern_name(name):
    return not name or name.startswith("Pattern ")


def _sample_default_color(getter, start, end, samples=5):
    """Sample the trailing slots to learn the per-theme 'untouched' color."""
    if end < start:
        return 0
    lo = max(start, end - samples + 1)
    counts = {}
    for i in range(lo, end + 1):
        try:
            c = getter(i) & 0xFFFFFF
            counts[c] = counts.get(c, 0) + 1
        except Exception:
            continue
    if not counts:
        return 0
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _cmd_get_project_state(params):
    """Extended project state with plugin identity, routing, slot counts,
    pattern length, selection state, and capabilities.

    See spec §4.1 for the response shape.
    """
    caps = _probe_capabilities()
    if not caps["_has_floor_core"]:
        return {
            "success": False,
            "error":   "FL_VERSION_UNSUPPORTED",
            "fl_version":  caps["fl_version"],
            "api_version": caps["api_version"],
        }

    import general
    import mixer
    import channels
    import patterns
    import playlist
    import transport

    t0 = time.time()
    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"
    is_playing = bool(transport.isPlaying())

    # ── Channels (always all) ─────────────────────────────────────
    channel_list = []
    for i in range(channels.channelCount()):
        try:
            color = channels.getChannelColor(i) & 0xFFFFFF
            volume = round(channels.getChannelVolume(i), 3)
            pan = round(channels.getChannelPan(i), 3)
            enabled = not bool(channels.isChannelMuted(i))
            insert = channels.getTargetFxTrack(i)
            channel_list.append({
                "index":   i,
                "name":    channels.getChannelName(i) or "",
                "color":   color,
                "volume":  volume,
                "pan":     pan,
                "enabled": enabled,
                "insert":  insert,
                "plugin":  _channel_plugin(i),
            })
        except Exception:
            pass

    # ── Mixer (filter; keep tracks with name OR color OR ≥1 slot OR ≥1 route) ──
    mixer_list = []
    mx_count = mixer.trackCount()
    mx_default_color = _sample_default_color(
        mixer.getTrackColor, 1, mx_count - 1
    ) if mx_count > 1 else 0
    for i in range(mx_count):
        try:
            name = mixer.getTrackName(i) or ""
            color = mixer.getTrackColor(i) & 0xFFFFFF
            slot_count = _mixer_slot_count(i)
            routes_to = _mixer_routes(i) if i > 0 else []  # Master rarely sends; cheap optimization
            is_default = (i != 0
                          and _is_default_mixer_name(name, i)
                          and color in (0, mx_default_color)
                          and slot_count == 0
                          and not routes_to)
            if is_default:
                continue
            mixer_list.append({
                "index":      i,
                "name":       name,
                "color":      color,
                "volume":     round(mixer.getTrackVolume(i), 3),
                "pan":        round(mixer.getTrackPan(i), 3),
                "muted":      bool(mixer.isTrackMuted(i)),
                "slot_count": slot_count,
                "routes_to":  routes_to,
            })
        except Exception:
            pass

    # ── Playlist tracks (1-indexed, filter defaults) ─────────────
    playlist_list = []
    pl_count = playlist.trackCount()
    pl_default_color = _sample_default_color(playlist.getTrackColor, 1, pl_count)
    for i in range(1, pl_count + 1):
        try:
            name = playlist.getTrackName(i) or ""
            color = playlist.getTrackColor(i) & 0xFFFFFF
            if _is_default_playlist_name(name) and color in (0, pl_default_color):
                continue
            playlist_list.append({"index": i, "name": name, "color": color})
        except Exception:
            pass

    # ── Patterns (1-indexed, filter defaults) ────────────────────
    pattern_list = []
    pat_count = patterns.patternCount()
    pat_default_color = _sample_default_color(patterns.getPatternColor, 1, pat_count)
    for i in range(1, pat_count + 1):
        try:
            name = patterns.getPatternName(i) or ""
            color = patterns.getPatternColor(i) & 0xFFFFFF
            if _is_default_pattern_name(name) and color in (0, pat_default_color):
                continue
            entry = {"index": i, "name": name, "color": color}
            if caps["has_pattern_length"]:
                try:
                    entry["length_beats"] = int(patterns.getPatternLength(i))
                except Exception:
                    pass
            pattern_list.append(entry)
        except Exception:
            pass

    elapsed = time.time() - t0
    marker = ""
    if elapsed > 18.0:
        marker = " !!! NEAR-TIMEOUT"
    elif elapsed > 10.0:
        marker = " !! SLOW"
    print(
        "[Studio AI] get_project_state: "
        "channels={} mixer={}/{} playlist={}/{} patterns={}/{} "
        "elapsed={:.3f}s{}".format(
            len(channel_list),
            len(mixer_list), mx_count,
            len(playlist_list), pl_count,
            len(pattern_list), pat_count,
            elapsed, marker,
        )
    )

    return {
        "bpm":             bpm,
        "project_name":    project_name,
        "playing":         is_playing,
        "channels":        channel_list,
        "mixer_tracks":    mixer_list,
        "playlist_tracks": playlist_list,
        "patterns":        pattern_list,
        "selection":       _selection(),
        "capabilities":    {k: v for k, v in caps.items() if not k.startswith("_")},
        "snapshot_at":     int(time.time()),
    }


# Register so device_studio_ai.py picks it up after Task 11 wires the dict.
INTROSPECT_HANDLERS["get_project_state"] = _cmd_get_project_state
```

- [ ] **Step 4: Run the new tests + the full file.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py -v
```
Expected: GetProjectStateTests passing (10/10), all earlier tests still passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): extended get_project_state with rich introspection

Adds plugin identity, mixer routing graph, slot counts, pattern
length, selection state, and capabilities to the project state
response. Filtering rule expanded to retain mixer tracks with
loaded slots or active outbound sends. Floor enforcement returns
FL_VERSION_UNSUPPORTED when getChannelType is absent.

Truncation envelope and include_routing flag arrive in next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Add `include_routing` flag and truncation envelope + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** Hard guardrails per spec §6.2 — `MAX_CHANNELS_INTROSPECTED`, `MAX_PATTERNS`, `MAX_RETAINED_INSERTS_FOR_ROUTING`, plus the user-controlled `include_routing` escape hatch. Surfaces `truncated_sections` and `routing_swept_through` per §6.2.

- [ ] **Step 1: Write failing tests.** Append:

```python
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
```

- [ ] **Step 2: Run — expect failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::TruncationTests -v
```

- [ ] **Step 3: Modify `_cmd_get_project_state` to add caps + flag.**

Above the function definition, add module constants:

```python
MAX_CHANNELS_INTROSPECTED        = 256
MAX_PATTERNS                     = 256
MAX_PLAYLIST_TRACKS              = 256
MAX_RETAINED_INSERTS_FOR_ROUTING = 100
```

Replace the body of `_cmd_get_project_state` to honor `include_routing` and apply caps. Replace the entire function with:

```python
def _cmd_get_project_state(params):
    """Extended project state with plugin identity, routing, slot counts,
    pattern length, selection state, and capabilities.

    Params:
      include_routing (bool, default True): if false, skip mixer routing
        sweep entirely (routes_to: [] for every track).

    Hard caps (see spec §6.2):
      MAX_CHANNELS_INTROSPECTED, MAX_PATTERNS, MAX_PLAYLIST_TRACKS,
      MAX_RETAINED_INSERTS_FOR_ROUTING. Truncation surfaces in
      `truncated_sections`.
    """
    caps = _probe_capabilities()
    if not caps["_has_floor_core"]:
        return {
            "success": False,
            "error":   "FL_VERSION_UNSUPPORTED",
            "fl_version":  caps["fl_version"],
            "api_version": caps["api_version"],
        }

    include_routing = bool((params or {}).get("include_routing", True))

    import general
    import mixer
    import channels
    import patterns
    import playlist
    import transport

    truncated_sections = []
    routing_swept_through = None

    t0 = time.time()
    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"
    is_playing = bool(transport.isPlaying())

    # ── Channels (cap at MAX_CHANNELS_INTROSPECTED) ───────────────
    channel_list = []
    ch_count_total = channels.channelCount()
    ch_count = min(ch_count_total, MAX_CHANNELS_INTROSPECTED)
    for i in range(ch_count):
        try:
            channel_list.append({
                "index":   i,
                "name":    channels.getChannelName(i) or "",
                "color":   channels.getChannelColor(i) & 0xFFFFFF,
                "volume":  round(channels.getChannelVolume(i), 3),
                "pan":     round(channels.getChannelPan(i), 3),
                "enabled": not bool(channels.isChannelMuted(i)),
                "insert":  channels.getTargetFxTrack(i),
                "plugin":  _channel_plugin(i),
            })
        except Exception:
            pass
    if ch_count_total > ch_count:
        truncated_sections.append("channels")

    # ── Mixer: pass 1 — filter retain set without routing ─────────
    mixer_list = []
    mx_count = mixer.trackCount()
    mx_default_color = _sample_default_color(
        mixer.getTrackColor, 1, mx_count - 1
    ) if mx_count > 1 else 0
    retained_for_routing = []
    for i in range(mx_count):
        try:
            name = mixer.getTrackName(i) or ""
            color = mixer.getTrackColor(i) & 0xFFFFFF
            slot_count = _mixer_slot_count(i)
            # Retain decision uses cheap signals first; routing-based retention
            # is computed in pass 2 if include_routing.
            retain_by_cheap = (
                i == 0  # Master always
                or not _is_default_mixer_name(name, i)
                or color not in (0, mx_default_color)
                or slot_count > 0
            )
            if retain_by_cheap:
                mixer_list.append({
                    "index":      i,
                    "name":       name,
                    "color":      color,
                    "volume":     round(mixer.getTrackVolume(i), 3),
                    "pan":        round(mixer.getTrackPan(i), 3),
                    "muted":      bool(mixer.isTrackMuted(i)),
                    "slot_count": slot_count,
                    "routes_to":  [],   # filled in pass 2
                })
                retained_for_routing.append(i)
        except Exception:
            pass

    # ── Mixer: pass 2 — routing sweep (if enabled, with cap) ──────
    if include_routing:
        if len(retained_for_routing) > MAX_RETAINED_INSERTS_FOR_ROUTING:
            truncated_sections.append("routing")
            sweep_indices = retained_for_routing[:MAX_RETAINED_INSERTS_FOR_ROUTING]
            routing_swept_through = sweep_indices[-1] if sweep_indices else None
        else:
            sweep_indices = retained_for_routing
        sweep_set = set(sweep_indices)
        for entry in mixer_list:
            if entry["index"] in sweep_set:
                entry["routes_to"] = _mixer_routes(entry["index"])
        # After routing, may discover MORE retained tracks (those with no
        # name/color/slots but ≥1 outbound route from a SWEPT track... no.
        # The current logic only retains a track if its OUTBOUND sweep returned
        # entries; we already counted those via slot_count/name/color or by
        # being included in sweep_indices. To catch tracks that survive only
        # by virtue of having outbound sends, do a second filter pass:
        survivors = []
        for entry in mixer_list:
            if (entry["index"] == 0  # Master always
                    or not _is_default_mixer_name(entry["name"], entry["index"])
                    or entry["color"] not in (0, mx_default_color)
                    or entry["slot_count"] > 0
                    or len(entry["routes_to"]) > 0):
                survivors.append(entry)
        mixer_list = survivors

    # ── Playlist tracks ──────────────────────────────────────────
    playlist_list = []
    pl_count = playlist.trackCount()
    pl_default_color = _sample_default_color(playlist.getTrackColor, 1, pl_count)
    for i in range(1, pl_count + 1):
        if len(playlist_list) >= MAX_PLAYLIST_TRACKS:
            truncated_sections.append("playlist_tracks")
            break
        try:
            name = playlist.getTrackName(i) or ""
            color = playlist.getTrackColor(i) & 0xFFFFFF
            if _is_default_playlist_name(name) and color in (0, pl_default_color):
                continue
            playlist_list.append({"index": i, "name": name, "color": color})
        except Exception:
            pass

    # ── Patterns ─────────────────────────────────────────────────
    pattern_list = []
    pat_count = patterns.patternCount()
    pat_default_color = _sample_default_color(patterns.getPatternColor, 1, pat_count)
    for i in range(1, pat_count + 1):
        if len(pattern_list) >= MAX_PATTERNS:
            truncated_sections.append("patterns")
            break
        try:
            name = patterns.getPatternName(i) or ""
            color = patterns.getPatternColor(i) & 0xFFFFFF
            if _is_default_pattern_name(name) and color in (0, pat_default_color):
                continue
            entry = {"index": i, "name": name, "color": color}
            if caps["has_pattern_length"]:
                try:
                    entry["length_beats"] = int(patterns.getPatternLength(i))
                except Exception:
                    pass
            pattern_list.append(entry)
        except Exception:
            pass

    elapsed = time.time() - t0
    marker = ""
    if elapsed > 18.0:
        marker = " !!! NEAR-TIMEOUT"
    elif elapsed > 10.0:
        marker = " !! SLOW"
    print(
        "[Studio AI] get_project_state: "
        "channels={} mixer={} playlist={} patterns={} "
        "elapsed={:.3f}s{}".format(
            len(channel_list), len(mixer_list),
            len(playlist_list), len(pattern_list),
            elapsed, marker,
        )
    )

    response = {
        "bpm":             bpm,
        "project_name":    project_name,
        "playing":         is_playing,
        "channels":        channel_list,
        "mixer_tracks":    mixer_list,
        "playlist_tracks": playlist_list,
        "patterns":        pattern_list,
        "selection":       _selection(),
        "capabilities":    {k: v for k, v in caps.items() if not k.startswith("_")},
        "snapshot_at":     int(time.time()),
    }
    if truncated_sections:
        response["truncated_sections"] = sorted(set(truncated_sections))
    if routing_swept_through is not None:
        response["routing_swept_through"] = routing_swept_through
    return response
```

- [ ] **Step 4: Run all introspect tests.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py -v
```
Expected: TruncationTests pass (5/5); previous tests still pass.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): truncation envelope + include_routing flag

Hard caps per spec §6.2: MAX_CHANNELS_INTROSPECTED=256,
MAX_PATTERNS=256, MAX_PLAYLIST_TRACKS=256,
MAX_RETAINED_INSERTS_FOR_ROUTING=100. truncated_sections in
response when caps fire. routing_swept_through marks the cutoff
index for partial routing graphs. include_routing=false skips
the routing sweep entirely as escape hatch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Implement `_cmd_get_mixer_chain` + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** On-demand effect-slot drill-down. See spec §4.2.

- [ ] **Step 1: Write failing tests.** Append:

```python
class GetMixerChainTests(unittest.TestCase):
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

    def test_returns_loaded_slots_with_names_and_color(self):
        self.mocks["plugins"].valid = {(7, 0): True, (7, 2): True}
        self.mocks["plugins"].names = {(7, 0): "Pro-Q 3", (7, 2): "Pro-C 2"}
        self.mocks["mixer"].slot_colors = {(7, 0): 0xFF0000, (7, 2): 0x00FF00}
        self.mocks["mixer"].slots_enabled = {7: True}
        result = self.module._cmd_get_mixer_chain({"index": 7})
        self.assertEqual(result["index"], 7)
        self.assertTrue(result["slots_enabled"])
        self.assertEqual(len(result["slots"]), 2)
        self.assertEqual(result["slots"][0]["plugin_name"], "Pro-Q 3")
        self.assertEqual(result["slots"][0]["color"], 0xFF0000)

    def test_skips_invalid_slots_silently(self):
        self.mocks["plugins"].valid = {(7, 0): True, (7, 5): True}
        self.mocks["plugins"].names = {(7, 0): "X", (7, 5): "Y"}
        result = self.module._cmd_get_mixer_chain({"index": 7})
        slot_indices = [s["slot_index"] for s in result["slots"]]
        self.assertEqual(slot_indices, [0, 5])

    def test_continues_past_per_slot_exception(self):
        def flaky(track, slot, useGlobalIndex=False):
            if slot == 3:
                raise RuntimeError("boom")
            return (track, slot) in {(7, 0), (7, 5)}
        self.mocks["plugins"].isValid = flaky
        self.mocks["plugins"].names = {(7, 0): "A", (7, 5): "B"}
        result = self.module._cmd_get_mixer_chain({"index": 7})
        slot_indices = [s["slot_index"] for s in result["slots"]]
        self.assertEqual(slot_indices, [0, 5])

    def test_invalid_track_index_returns_error(self):
        result = self.module._cmd_get_mixer_chain({"index": 200})
        self.assertEqual(result.get("success"), False)
        self.assertEqual(result.get("error"), "INVALID_TRACK_INDEX")
        self.assertEqual(result.get("track_count"), 127)

    def test_omits_color_when_capability_absent(self):
        del self.mocks["mixer"].getSlotColor
        self.mocks["plugins"].valid = {(7, 0): True}
        self.mocks["plugins"].names = {(7, 0): "P"}
        result = self.module._cmd_get_mixer_chain({"index": 7})
        self.assertNotIn("color", result["slots"][0])

    def test_slots_enabled_reflects_track_state(self):
        self.mocks["plugins"].valid = {(7, 0): True}
        self.mocks["plugins"].names = {(7, 0): "P"}
        self.mocks["mixer"].slots_enabled = {7: False}
        result = self.module._cmd_get_mixer_chain({"index": 7})
        self.assertFalse(result["slots_enabled"])
```

- [ ] **Step 2: Run — expect failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::GetMixerChainTests -v
```

- [ ] **Step 3: Implement.** In `handlers_introspect.py`, after `_cmd_get_project_state`:

```python
def _cmd_get_mixer_chain(params):
    """Effect-slot enumeration for one mixer track.

    Returns:
      Out-of-range: {success: False, error: "INVALID_TRACK_INDEX", track_count: N}
      Valid: {index, slots_enabled, slots: [...]}
    """
    import mixer
    import plugins
    track = int((params or {}).get("index", 0))
    track_count = mixer.trackCount()
    if track < 0 or track >= track_count:
        return {
            "success":     False,
            "error":       "INVALID_TRACK_INDEX",
            "track_count": track_count,
        }

    has_slot_color = hasattr(mixer, "getSlotColor")
    slots_enabled = True
    try:
        slots_enabled = bool(mixer.isTrackSlotsEnabled(track))
    except Exception:
        pass

    slots = []
    for slot in range(10):
        try:
            if not bool(plugins.isValid(track, slot)):
                continue
        except Exception:
            continue
        try:
            entry = {
                "slot_index":  slot,
                "plugin_name": plugins.getPluginName(track, slot) or "",
            }
            if has_slot_color:
                try:
                    entry["color"] = int(mixer.getSlotColor(track, slot)) & 0xFFFFFF
                except Exception:
                    pass
            slots.append(entry)
        except Exception:
            continue

    return {"index": track, "slots_enabled": slots_enabled, "slots": slots}


INTROSPECT_HANDLERS["get_mixer_chain"] = _cmd_get_mixer_chain
```

- [ ] **Step 4: Run.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::GetMixerChainTests -v
```
Expected: 6/6 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): get_mixer_chain handler

Effect-slot drill-down for one mixer track. Validates index
range with INVALID_TRACK_INDEX, surfaces track-level
slots_enabled, includes per-slot color when FL ≥32.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Implement `_dump_plugin_params` helper + two registered handlers + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** Drill-down for plugin parameters with hung-VST guard. See spec §4.3.

- [ ] **Step 1: Write failing tests.** Append:

```python
class PluginParamsTests(unittest.TestCase):
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

    def _setup_plugin(self, target, slot, name, param_count):
        self.mocks["plugins"].valid[(target, slot)] = True
        self.mocks["plugins"].names[(target, slot)] = name
        self.mocks["plugins"].param_counts[(target, slot)] = param_count
        for i in range(param_count):
            self.mocks["plugins"].param_names[(target, slot, i)] = f"P{i}"
            self.mocks["plugins"].param_values[(target, slot, i)] = i / max(param_count, 1)

    def test_mixer_plugin_params_returns_full_dump_within_cap(self):
        self._setup_plugin(7, 0, "Pro-Q 3", 12)
        result = self.module._cmd_get_mixer_plugin_params({
            "track_index": 7, "slot_index": 0,
        })
        self.assertEqual(result["plugin_name"], "Pro-Q 3")
        self.assertEqual(result["param_count"], 12)
        self.assertEqual(result["returned_count"], 12)
        self.assertFalse(result["truncated"])

    def test_mixer_plugin_params_truncates_at_max_params(self):
        self._setup_plugin(7, 0, "Serum", 800)
        result = self.module._cmd_get_mixer_plugin_params({
            "track_index": 7, "slot_index": 0, "max_params": 64,
        })
        self.assertEqual(result["param_count"], 800)
        self.assertEqual(result["returned_count"], 64)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncated_reason"], "MAX_PARAMS")

    def test_mixer_plugin_params_invalid_target(self):
        # No valid entry for (7, 0)
        result = self.module._cmd_get_mixer_plugin_params({
            "track_index": 7, "slot_index": 0,
        })
        self.assertEqual(result.get("success"), False)
        self.assertEqual(result.get("error"), "INVALID_TARGET")

    def test_channel_plugin_params_for_sampler_returns_invalid_target(self):
        # Sampler at channel 0 with no plugin instance
        # plugins.isValid((0, -1)) returns False by default
        result = self.module._cmd_get_channel_plugin_params({"channel_index": 0})
        self.assertEqual(result.get("success"), False)
        self.assertEqual(result.get("error"), "INVALID_TARGET")

    def test_channel_plugin_params_returns_full_dump(self):
        self._setup_plugin(3, -1, "Sytrus", 100)
        result = self.module._cmd_get_channel_plugin_params({
            "channel_index": 3, "max_params": 50,
        })
        self.assertEqual(result["plugin_name"], "Sytrus")
        self.assertEqual(result["returned_count"], 50)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncated_reason"], "MAX_PARAMS")

    def test_per_param_failure_continues(self):
        self._setup_plugin(7, 0, "Buggy", 5)
        # param 2 raises
        self.mocks["plugins"]._raise_on_param.add((7, 0, 2))
        result = self.module._cmd_get_mixer_plugin_params({
            "track_index": 7, "slot_index": 0,
        })
        # 4 params returned (indices 0,1,3,4); param 2 skipped
        self.assertEqual(result["returned_count"], 4)
        param_indices = [p["index"] for p in result["params"]]
        self.assertEqual(param_indices, [0, 1, 3, 4])

    def test_time_budget_truncates_when_plugin_hangs(self):
        self._setup_plugin(7, 0, "HungVST", 100)
        # 0.05s per param × 100 params = 5s — well over the 2s budget.
        # Budget check runs every 8 params; expect ~16-24 params returned.
        self.mocks["plugins"]._sleep_per_param_s = 0.05
        result = self.module._cmd_get_mixer_plugin_params({
            "track_index": 7, "slot_index": 0,
        })
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncated_reason"], "TIME_BUDGET")
        self.assertLess(result["returned_count"], 100)
```

- [ ] **Step 2: Run — expect failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::PluginParamsTests -v
```

- [ ] **Step 3: Implement.** In `handlers_introspect.py`, after `_cmd_get_mixer_chain`:

```python
PARAM_TIME_BUDGET_S    = 2.0
PARAM_TIME_CHECK_EVERY = 8


def _dump_plugin_params(target, slot, max_params):
    """Dump up to max_params params for the (target, slot) plugin.

    target = mixer track index when slot >= 0
    target = channel rack index when slot == -1
    """
    import plugins
    start = time.time()

    try:
        if not bool(plugins.isValid(target, slot)):
            return {"success": False, "error": "INVALID_TARGET"}
    except Exception:
        return {"success": False, "error": "INVALID_TARGET"}

    name = ""
    try:
        name = plugins.getPluginName(target, slot) or ""
    except Exception:
        pass
    try:
        full_count = int(plugins.getParamCount(target, slot))
    except Exception:
        full_count = 0

    n = min(full_count, int(max_params))
    out = []
    truncated_reason = None

    for i in range(n):
        if i and (i % PARAM_TIME_CHECK_EVERY == 0):
            if time.time() - start > PARAM_TIME_BUDGET_S:
                truncated_reason = "TIME_BUDGET"
                break
        try:
            param = {
                "index": i,
                "name":  plugins.getParamName(i, target, slot) or "",
                "value": round(float(plugins.getParamValue(i, target, slot)), 4),
            }
            try:
                vs = plugins.getParamValueString(i, target, slot)
                if vs:
                    param["value_string"] = str(vs)
            except Exception:
                pass
            out.append(param)
        except Exception:
            continue

    if truncated_reason is None and full_count > len(out):
        truncated_reason = "MAX_PARAMS"

    elapsed_ms = int((time.time() - start) * 1000)
    return {
        "plugin_name":      name,
        "param_count":      full_count,
        "returned_count":   len(out),
        "truncated":        truncated_reason is not None,
        "truncated_reason": truncated_reason,
        "elapsed_ms":       elapsed_ms,
        "params":           out,
    }


def _cmd_get_mixer_plugin_params(params):
    track = int((params or {}).get("track_index", 0))
    slot  = int((params or {}).get("slot_index", 0))
    max_params = max(1, min(500, int((params or {}).get("max_params", 64))))
    result = _dump_plugin_params(track, slot, max_params)
    if result.get("success") is None:  # success = no error key set
        result["track_index"] = track
        result["slot_index"]  = slot
    return result


def _cmd_get_channel_plugin_params(params):
    channel = int((params or {}).get("channel_index", 0))
    max_params = max(1, min(500, int((params or {}).get("max_params", 64))))
    result = _dump_plugin_params(channel, -1, max_params)
    if result.get("success") is None:
        result["channel_index"] = channel
    return result


INTROSPECT_HANDLERS["get_mixer_plugin_params"]   = _cmd_get_mixer_plugin_params
INTROSPECT_HANDLERS["get_channel_plugin_params"] = _cmd_get_channel_plugin_params
```

- [ ] **Step 4: Run.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::PluginParamsTests -v
```
Expected: 7/7 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): plugin params handlers with hung-VST guard

Two registered actions sharing _dump_plugin_params helper:
- get_mixer_plugin_params for mixer-slot plugins
- get_channel_plugin_params for channel-rack plugins
Wall-clock budget of 2s neutralizes UI-thread-hung VSTs;
truncated_reason distinguishes MAX_PARAMS vs TIME_BUDGET.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Implement `_cmd_get_mixer_eq` + tests

**Files:**
- Modify: `bridge/fl_studio/handlers_introspect.py`
- Modify: `bridge/fl_studio/tests/test_handlers_introspect.py`

**Why:** 3-band EQ readout per spec §4.4.

- [ ] **Step 1: Write failing tests.** Append:

```python
class GetMixerEqTests(unittest.TestCase):
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

    def test_returns_unavailable_when_capability_missing(self):
        del self.mocks["mixer"].getEqGain
        result = self.module._cmd_get_mixer_eq({"index": 5})
        self.assertEqual(result["index"], 5)
        self.assertFalse(result["available"])
        self.assertNotIn("bands", result)

    def test_returns_three_bands_when_available(self):
        self.mocks["mixer"].eq = {
            (5, 0): {"gain": 0.6, "freq": 0.2, "bw": 0.5},
            (5, 1): {"gain": 0.5, "freq": 0.5, "bw": 0.5},
            (5, 2): {"gain": 0.7, "freq": 0.8, "bw": 0.3},
        }
        result = self.module._cmd_get_mixer_eq({"index": 5})
        self.assertTrue(result["available"])
        self.assertEqual(set(result["bands"].keys()), {"low", "mid", "high"})
        self.assertEqual(result["bands"]["low"]["gain"], 0.6)
        self.assertEqual(result["bands"]["high"]["freq"], 0.8)

    def test_per_band_failure_falls_back_to_neutral(self):
        original_freq = self.mocks["mixer"].getEqFrequency
        def freq_flaky(track, band):
            if band == 1:
                raise RuntimeError("mid band broken")
            return original_freq(track, band)
        self.mocks["mixer"].getEqFrequency = freq_flaky
        result = self.module._cmd_get_mixer_eq({"index": 5})
        self.assertTrue(result["available"])
        self.assertEqual(result["bands"]["mid"]["freq"], 0.5)  # fallback
```

- [ ] **Step 2: Run — expect failures.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::GetMixerEqTests -v
```

- [ ] **Step 3: Implement.** Append to `handlers_introspect.py`:

```python
def _cmd_get_mixer_eq(params):
    """Read the 3-band EQ on one mixer track.

    Returns {index, available: false} on FL <2024 (capability absent).
    """
    import mixer
    caps = _probe_capabilities()
    track = int((params or {}).get("index", 0))
    if not caps["has_eq_getters"]:
        return {"index": track, "available": False}

    bands = {}
    for band_name, band_idx in (("low", 0), ("mid", 1), ("high", 2)):
        try:
            gain = round(float(mixer.getEqGain(track, band_idx)), 4)
        except Exception:
            gain = 0.5
        try:
            freq = round(float(mixer.getEqFrequency(track, band_idx)), 4)
        except Exception:
            freq = 0.5
        try:
            bw = round(float(mixer.getEqBandwidth(track, band_idx)), 4)
        except Exception:
            bw = 0.5
        bands[band_name] = {"gain": gain, "freq": freq, "bw": bw}

    return {"index": track, "available": True, "bands": bands}


INTROSPECT_HANDLERS["get_mixer_eq"] = _cmd_get_mixer_eq
```

- [ ] **Step 4: Run.**

```bash
cd bridge/fl_studio && python -m pytest tests/test_handlers_introspect.py::GetMixerEqTests -v
```
Expected: 3/3 passing.

- [ ] **Step 5: Commit.**

```bash
git add bridge/fl_studio/handlers_introspect.py bridge/fl_studio/tests/test_handlers_introspect.py
git commit -m "$(cat <<'EOF'
feat(bridge): get_mixer_eq handler

3-band EQ readout for one mixer track. Returns
{available: false} on FL <2024. Per-band failures fall
back to neutral 0.5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Wire `INTROSPECT_HANDLERS` into `device_studio_ai.py`

**Files:**
- Modify: `bridge/fl_studio/device_studio_ai.py`

**Why:** Without this, the new handlers are unreachable from the relay. Last bridge-side wiring step.

- [ ] **Step 1: Read the current device_studio_ai.py to confirm the handler-registry pattern.**

```bash
grep -n "HANDLERS" bridge/fl_studio/device_studio_ai.py
```

- [ ] **Step 2: Add the import and merge the dict.**

In `bridge/fl_studio/device_studio_ai.py`, add to the imports near line 50:

```python
from handlers_introspect import INTROSPECT_HANDLERS
```

Update the `_HANDLERS` dict near line 328 — replace:

```python
_HANDLERS = {
    "set_bpm": _cmd_set_bpm,
    "get_state": _cmd_get_state,
    "get_project_state": _cmd_get_state,
    "add_track": _cmd_add_track,
    "play": _cmd_play,
    "stop": _cmd_stop,
    "record": _cmd_record,
    "set_track_volume": _cmd_set_track_volume,
    "set_track_pan": _cmd_set_track_pan,
    "set_track_mute": _cmd_set_track_mute,
    "set_track_solo": _cmd_set_track_solo,
    "rename_track": _cmd_rename_track,
    **ORGANIZE_HANDLERS,
    **BULK_HANDLERS,
}
```

with:

```python
_HANDLERS = {
    "set_bpm": _cmd_set_bpm,
    "get_state": _cmd_get_state,           # legacy alias retained
    "get_project_state": _cmd_get_state,   # overridden below by INTROSPECT_HANDLERS
    "add_track": _cmd_add_track,
    "play": _cmd_play,
    "stop": _cmd_stop,
    "record": _cmd_record,
    "set_track_volume": _cmd_set_track_volume,
    "set_track_pan": _cmd_set_track_pan,
    "set_track_mute": _cmd_set_track_mute,
    "set_track_solo": _cmd_set_track_solo,
    "rename_track": _cmd_rename_track,
    **ORGANIZE_HANDLERS,
    **BULK_HANDLERS,
    **INTROSPECT_HANDLERS,                 # MUST be last so its
                                           # get_project_state wins.
}
```

- [ ] **Step 3: Run the existing device_studio_ai test (if present) and the full bridge suite.**

```bash
cd bridge/fl_studio && python -m pytest tests/ -v
```
Expected: all green, including the existing organize/bulk tests.

- [ ] **Step 4: Commit.**

```bash
git add bridge/fl_studio/device_studio_ai.py
git commit -m "$(cat <<'EOF'
feat(bridge): register INTROSPECT_HANDLERS

Wires the tier 2 introspection handlers into the dispatch table.
Order ensures the new get_project_state overrides the legacy
alias from _cmd_get_state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Web tool registry

### Task 15: Extend `get_project_state` tool with `include_routing` parameter

**Files:**
- Modify: `apps/web/src/lib/ai/tools/project.ts`

**Why:** Web-side schema for the new optional flag. See spec §8.1.

- [ ] **Step 1: Read current file.**

```bash
cat apps/web/src/lib/ai/tools/project.ts
```

- [ ] **Step 2: Replace the `get_project_state` definition.** In `apps/web/src/lib/ai/tools/project.ts`:

```ts
// apps/web/src/lib/ai/tools/project.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description:
        "Snapshot of the FL Studio project: BPM, channels (with plugin identity), " +
        "mixer tracks (with effect-slot counts and routing graph), playlist tracks, " +
        "patterns (with length), current selection, and FL capabilities. " +
        "Call ONCE at the start of any organize task — do NOT re-call within the same " +
        "turn after the user has agreed to a plan; the user agreed to what you summarized, " +
        "not to a re-fetch.",
      inputSchema: z.object({
        include_routing: z
          .boolean()
          .optional()
          .default(true)
          .describe(
            "Include per-mixer-track outbound routing graph. Default true. " +
            "Pass false for a fast cold-start summary, or when a prior call returned " +
            "truncated_sections containing 'routing'.",
          ),
      }),
      toRelay: ({ include_routing }) => ({
        action: "get_project_state",
        params: { include_routing },
      }),
    }),

    undo: relayTool(userId, {
      description:
        "Undo the most recent change in FL Studio (uses FL's native undo history). " +
        "After applying an organization plan, this reverts the entire batch as one step. " +
        "Pass `count` only when a previous `apply_organization_plan` returned " +
        "`undo_grouped: false` — then pass that response's `op_count`.",
      inputSchema: z.object({
        count: z
          .number()
          .int()
          .min(1)
          .max(2000)
          .optional()
          .describe(
            "Number of undo steps. Default 1. Only set when a prior " +
            "apply_organization_plan returned undo_grouped:false.",
          ),
      }),
      toRelay: ({ count }) => ({
        action: "undo",
        params: count !== undefined ? { count } : {},
      }),
    }),
  };
}
```

- [ ] **Step 3: Verify tsc.**

```bash
cd apps/web && bunx tsc --noEmit
```

- [ ] **Step 4: Commit.**

```bash
git add apps/web/src/lib/ai/tools/project.ts
git commit -m "$(cat <<'EOF'
feat(web): get_project_state gains include_routing flag

Optional boolean (default true). Allows the AI to request a
fast cold-start probe by passing false. Tool description warns
against in-turn re-fetch (heads off the scaffold-drift bug analog).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: Add new tools to `mixer.ts`

**Files:**
- Modify: `apps/web/src/lib/ai/tools/mixer.ts`

**Why:** Three new on-demand drill-down tools. See spec §8.2.

- [ ] **Step 1: Read current file.**

```bash
cat apps/web/src/lib/ai/tools/mixer.ts
```

- [ ] **Step 2: Append the three new tools.** Add inside the `mixerTools` return object (before the closing `};`):

```ts
    get_mixer_chain: relayTool(userId, {
      description:
        "List the effect-plugin chain on one mixer track (slot index → plugin name + " +
        "color, plus a track-level slots_enabled flag). Use this to inspect signal " +
        "chains — the vocal chain, drum-bus processing, mastering chain, etc. Returns " +
        "{ success: false, error: 'INVALID_TRACK_INDEX' } if the index is out of range.",
      inputSchema: z.object({ index: MX_INDEX }),
      toRelay: ({ index }) => ({ action: "get_mixer_chain", params: { index } }),
    }),

    get_mixer_plugin_params: relayTool(userId, {
      description:
        "Dump parameter values for one plugin in a mixer slot. Use sparingly — large " +
        "VSTs report hundreds of params. Default cap is 64; raise max_params only when " +
        "you specifically need a deeper read. May return truncated_reason: 'TIME_BUDGET' " +
        "if the plugin's GUI thread is hung; surface that honestly to the user.",
      inputSchema: z.object({
        track_index: MX_INDEX,
        slot_index: z.number().int().min(0).max(9),
        max_params: z.number().int().min(1).max(500).optional().default(64),
      }),
      toRelay: ({ track_index, slot_index, max_params }) => ({
        action: "get_mixer_plugin_params",
        params: { track_index, slot_index, max_params },
      }),
    }),

    get_mixer_eq: relayTool(userId, {
      description:
        "Read the 3-band EQ values (low/mid/high) for one mixer track. Returns " +
        "{ available: false } on FL versions older than 2024 — check before using values.",
      inputSchema: z.object({ index: MX_INDEX }),
      toRelay: ({ index }) => ({ action: "get_mixer_eq", params: { index } }),
    }),
```

- [ ] **Step 3: Verify tsc.**

```bash
cd apps/web && bunx tsc --noEmit
```

- [ ] **Step 4: Commit.**

```bash
git add apps/web/src/lib/ai/tools/mixer.ts
git commit -m "$(cat <<'EOF'
feat(web): add get_mixer_chain, get_mixer_plugin_params, get_mixer_eq

Three new on-demand introspection tools. Effect-chain enumeration,
generic plugin param dump (with hung-VST guard surfaced via
truncated_reason), and 3-band EQ readout (FL 2024+).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: Add `get_channel_plugin_params` to `channels.ts`

**Files:**
- Modify: `apps/web/src/lib/ai/tools/channels.ts`

**Why:** Channel-rack variant of plugin param dump. See spec §8.3.

- [ ] **Step 1: Append the new tool inside `channelTools`'s return object** (before the closing `};`):

```ts
    get_channel_plugin_params: relayTool(userId, {
      description:
        "Dump parameter values for the plugin loaded on one channel rack entry. " +
        "Same caveats as get_mixer_plugin_params. Returns " +
        "{ success: false, error: 'INVALID_TARGET' } if the channel has no plugin " +
        "(e.g. a Sampler channel with no instrument).",
      inputSchema: z.object({
        channel_index: CH_INDEX,
        max_params: z.number().int().min(1).max(500).optional().default(64),
      }),
      toRelay: ({ channel_index, max_params }) => ({
        action: "get_channel_plugin_params",
        params: { channel_index, max_params },
      }),
    }),
```

- [ ] **Step 2: Verify tsc.**

```bash
cd apps/web && bunx tsc --noEmit
```

- [ ] **Step 3: Commit.**

```bash
git add apps/web/src/lib/ai/tools/channels.ts
git commit -m "$(cat <<'EOF'
feat(web): add get_channel_plugin_params

Channel-rack variant of plugin param dump. Returns INVALID_TARGET
on Sampler channels with no instrument loaded (split-tool design
from spec §4.3 to avoid empty-response trap).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: Update `composeTools.test.ts` snapshot

**Files:**
- Modify: `apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts`

**Why:** Regression guard for the tool list. New tools must appear; legacy `get_capabilities` must NOT (it's intentionally not exposed). See spec §11.2.

- [ ] **Step 1: Read the current test.**

```bash
cat apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts
```

- [ ] **Step 2: Update the snapshot.** Add the four new tool names to whatever expected-keys list the snapshot maintains. Look for an array or `Object.keys(...)` assertion. Insert these names alphabetically:

- `get_channel_plugin_params`
- `get_mixer_chain`
- `get_mixer_eq`
- `get_mixer_plugin_params`

If the test uses `toMatchSnapshot()` with the inline snapshot file, run `bunx vitest run -u` once after the implementation lands to update; verify the diff manually before committing.

If the test does explicit key assertions, replace the relevant array literal accordingly.

- [ ] **Step 3: Add an `include_routing` schema regression assertion.** Append a new `it()` block:

```ts
  it("get_project_state accepts include_routing in its inputSchema", () => {
    const tools = composeTools("test-user");
    const tool = tools.get_project_state;
    // tool.inputSchema is a Zod schema; safeParse with include_routing.
    const result = (tool as { inputSchema: { safeParse: (v: unknown) => { success: boolean } } })
      .inputSchema.safeParse({ include_routing: false });
    expect(result.success).toBe(true);
    const result2 = (tool as { inputSchema: { safeParse: (v: unknown) => { success: boolean } } })
      .inputSchema.safeParse({});
    expect(result2.success).toBe(true);  // optional
  });
```

(Adjust types/imports based on what the existing test file already imports.)

- [ ] **Step 4: Run the test.**

```bash
cd apps/web && bun run test
```
Expected: all green.

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts
git commit -m "$(cat <<'EOF'
test(web): composeTools snapshot covers tier 2 tools

Asserts presence of get_mixer_chain, get_mixer_plugin_params,
get_channel_plugin_params, get_mixer_eq. Asserts get_capabilities
is intentionally absent. Adds include_routing schema regression
guard on get_project_state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — System prompt and AI evals

### Task 19: Update `system-prompt.ts` with new context section + worked examples + anti-refetch rule

**Files:**
- Modify: `apps/web/src/lib/ai/system-prompt.ts`

**Why:** Models tend to keep using whichever tools they had embedded. The prompt update + worked examples are the lever to make the AI actually USE the new context. See spec §9.

- [ ] **Step 1: Read the current prompt.**

```bash
cat apps/web/src/lib/ai/system-prompt.ts
```

- [ ] **Step 2: Append the new section.** Edit `apps/web/src/lib/ai/system-prompt.ts`. Add the following text inside the SYSTEM_PROMPT template literal, immediately AFTER the existing "# Tone" section (so it's the last content before the closing backtick):

```text


# Reading project context

\`get_project_state\` returns rich structural context. Use it once at the start of any organize task. **Do NOT call get_project_state twice within the same conversation turn:** if you've shown the user a summary built from one snapshot and they agreed to act, re-fetching produces a slightly different snapshot (the user may have clicked something) and the plan you apply may not match what the user agreed to.

What's in the response:
- BPM, project name, playing state.
- channels[]: each has plugin: { name, type_label } where type_label is one of "sampler" | "hybrid" | "vst" | "automation" | "layer" | "midi_out" | "unknown". Use the plugin name and type_label to infer role.
- mixer_tracks[]: each has slot_count (# of loaded effect plugins) and routes_to[] (outbound sends — list of { to_index, level? }). Tracks with many inbound routes from drum channels are likely the drum bus.
- patterns[]: each has length_beats when available.
- selection: { channel_index, pattern_index, mixer_track_index } — what the user is currently focused on.
- capabilities: which FL features are available. If capabilities.has_send_levels is false, level fields are absent from routes_to[]. If capabilities.has_eq_getters is false, get_mixer_eq returns { available: false }. NEVER invent numbers that aren't in the response.
- truncated_sections (optional): if present, the project exceeded enumeration caps. Tell the user honestly which sections are partial.

For per-track effect-chain detail use get_mixer_chain(index). For one plugin's parameter readout use get_mixer_plugin_params or get_channel_plugin_params — but only when you specifically need it (e.g. detecting duplicate EQs, surfacing the gain on a vocal chain comp). These calls have a 2-second wall-clock budget; if a plugin's GUI thread hangs, the response will have truncated_reason: "TIME_BUDGET" — surface that ("Looks like that plugin's UI is hung, I only got partial readings").

# Worked examples

User: "What kind of synth is on channel 5?"
You: [If you don't already have project state in this turn, call get_project_state. Then read channels[5].plugin.] "Channel 5 is a Sytrus. Want me to inspect its params?"

User: "What's on my master?"
You: [Call get_mixer_chain(0).] "Your master has 3 plugins: Fruity Limiter, Youlean Loudness Meter, Soundgoodizer."

User: "Where's my drum bus?"
You: [Use routing from get_project_state. Find the mixer track with the most inbound routes from channels.] "Inserts 1-6 all route to Insert 7, named 'DRUMS' — that's your drum bus. It has 4 effect slots loaded."

User: "Are there duplicate EQs anywhere?"
You: [Get project state. For each mixer track with slot_count > 1, call get_mixer_chain. Look for repeated plugin names within the same chain.] "Found one: Insert 12 has Fruity Parametric EQ 2 in slots 0 and 2. Want me to highlight which slot to remove?"

User: "What's the vocal chain look like?"
You: [Call find_mixer_track_by_name("vocal"), then get_mixer_chain on the top match.] "Vocal chain on Insert 22: Fruity Limiter, Pro-DS, Pro-Q 3, Pro-C 2. Outbound send to Insert 88." (Do not invent role labels like "de-esser" or "compressor" — only report what get_mixer_chain returns.)
```

(Note: the backslashes before backticks are escapes for the surrounding template literal — preserve them.)

- [ ] **Step 3: Verify tsc.**

```bash
cd apps/web && bunx tsc --noEmit
```

- [ ] **Step 4: Run the full web test suite.**

```bash
cd apps/web && bun run test
```

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/lib/ai/system-prompt.ts
git commit -m "$(cat <<'EOF'
feat(web): system prompt teaches tier 2 introspection

Documents the new project-state shape, anti-refetch rule, and
five worked examples covering synth ID, master chain, drum bus,
duplicate-EQ detection, and vocal chain. Worked examples are
the lever that prevents the model from defaulting to old habits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 20: Add response-content evals

**Files:**
- Locate: existing eval suite directory (check `apps/web/src/lib/ai/__evals__/` or `apps/web/src/lib/ai/__tests__/`)
- Create or modify the eval file accordingly.

**Why:** Tool-selection evals can pass while the model produces generic text that ignores the new fields. Response-content assertions are what prove Tier 2 actually moved the needle. See spec §11.3.

- [ ] **Step 1: Locate the eval suite.**

```bash
find apps/web/src/lib/ai -name "*eval*" -o -name "__evals__" 2>/dev/null
```

If no eval suite exists yet, create the directory and a starter file:

```bash
mkdir -p apps/web/src/lib/ai/__evals__
```

- [ ] **Step 2: Create the eval file.**

`apps/web/src/lib/ai/__evals__/tier2-introspection.eval.ts`:

```ts
/**
 * Local-only AI eval for tier 2 introspection.
 *
 * Run via: bunx vitest run apps/web/src/lib/ai/__evals__/tier2-introspection.eval.ts
 *
 * Requires GEMINI_API_KEY (or whatever provider key the chat agent uses).
 * Skipped automatically when the key is absent — DO NOT block CI on this.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { streamText, convertToModelMessages, stepCountIs } from "ai";
import { google } from "@ai-sdk/google";
import { SYSTEM_PROMPT } from "../system-prompt";

// Skip when no API key — keeps CI green.
const SKIP = !process.env.GEMINI_API_KEY;

// Fixture project state (matches the EnhancedProjectState shape but is small).
const fixture = {
  bpm: 128,
  project_name: "EvalProj",
  playing: false,
  channels: [
    { index: 0, name: "Kick", color: 0xFF0000, volume: 0.78, pan: 0, enabled: true, insert: 1, plugin: { name: "Sampler", type: 0, type_label: "sampler" } },
    { index: 5, name: "Lead", color: 0x00FF00, volume: 0.6, pan: 0, enabled: true, insert: 9, plugin: { name: "Sytrus", type: 2, type_label: "vst" } },
    { index: 12, name: "Pad", color: 0x0000FF, volume: 0.5, pan: 0, enabled: true, insert: 11, plugin: { name: "FLEX", type: 2, type_label: "vst" } },
  ],
  mixer_tracks: [
    { index: 0, name: "Master", color: 0, volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [] },
    { index: 1, name: "Kick",   color: 0, volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [{ to_index: 7 }] },
    { index: 2, name: "Snare",  color: 0, volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [{ to_index: 7 }] },
    { index: 3, name: "Hat",    color: 0, volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [{ to_index: 7 }] },
    { index: 7, name: "DRUMS",  color: 0xFF0000, volume: 0.8, pan: 0, muted: false, slot_count: 4, routes_to: [] },
    { index: 22, name: "Vocal", color: 0xD53F8C, volume: 0.7, pan: 0, muted: false, slot_count: 6, routes_to: [{ to_index: 88 }] },
  ],
  playlist_tracks: [],
  patterns: [],
  selection: { channel_index: null, pattern_index: null, mixer_track_index: null },
  capabilities: {
    fl_version: "21.2.3", api_version: 36,
    has_send_levels: true, has_eq_getters: true, has_save_undo: true,
    has_pattern_length: true, has_slot_color: true,
  },
  snapshot_at: 0,
};

async function runChat(userMsg: string): Promise<string> {
  // Mock the relay so get_project_state returns our fixture.
  const tools = {
    get_project_state: {
      description: "fixture",
      inputSchema: { safeParse: () => ({ success: true, data: {} }) } as any,
      execute: async () => ({ success: true, data: fixture }),
    },
  } as any;

  const result = await streamText({
    model: google("gemini-2.5-flash"),
    system: SYSTEM_PROMPT,
    messages: await convertToModelMessages([{ role: "user", parts: [{ type: "text", text: userMsg }] }] as any),
    tools,
    stopWhen: stepCountIs(5),
  });

  let fullText = "";
  for await (const chunk of result.textStream) {
    fullText += chunk;
  }
  return fullText;
}

describe.skipIf(SKIP)("tier 2 response-content evals", () => {
  it("'what synths am I using?' mentions Sytrus and FLEX", async () => {
    const reply = await runChat("What synths am I using?");
    expect(reply).toMatch(/sytrus/i);
    expect(reply).toMatch(/flex/i);
  }, 60_000);

  it("'where's my drum bus?' mentions Insert 7 or DRUMS", async () => {
    const reply = await runChat("Where's my drum bus?");
    expect(reply).toMatch(/insert\s*7|drums/i);
  }, 60_000);

  it("'tell me about insert 22' mentions slot count", async () => {
    const reply = await runChat("Tell me about insert 22");
    expect(reply).toMatch(/\b6\b\s*(slot|plugin|effect|insert)/i);
  }, 60_000);
});
```

(Adjust the chat-agent invocation to match how `apps/web/src/app/api/ai/execute/route.ts` constructs `streamText` — the import paths and `tools` factory. The above is structurally correct but you may need to import `composeTools` from `../tools` and provide a relay mock.)

- [ ] **Step 3: Run the eval locally** (only when `GEMINI_API_KEY` is set):

```bash
cd apps/web && GEMINI_API_KEY=... bunx vitest run src/lib/ai/__evals__/tier2-introspection.eval.ts
```
Expected (when key present): 3/3 passing. The substring assertions are intentionally lenient on phrasing but strict on content.

- [ ] **Step 4: Run the broader test suite to confirm no regression** (skipped evals don't fail):

```bash
cd apps/web && bun run test
```

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/lib/ai/__evals__/
git commit -m "$(cat <<'EOF'
test(web): tier 2 response-content evals

Three local-only evals that assert the AI's TEXT response uses
the new project-state fields (plugin names, routing, slot counts)
rather than producing generic replies. Skipped without
GEMINI_API_KEY so CI stays green.

This is the test that proves tier 2 actually moved the needle —
tool-selection evals alone can pass while content regresses.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Verification

### Task 21: Manual smoke test on real FL Studio (merge gate)

**Files:** None (operational task)

**Why:** Spec §11.4 — the perf merge gate is real. The `<12 s median, <16 s max` budget is unverified until measured.

- [ ] **Step 1: Build a heavy test project.**

In FL Studio (macOS preferred per existing smoke test history):
- 40 channels (mix of Sampler, Sytrus, FLEX, Serum)
- 60 retained mixer inserts including:
  - Vocal chain on one insert (≥6 plugins)
  - Drum bus with 6 inbound routes
- 30 named patterns
- 30 colored playlist tracks

- [ ] **Step 2: Measure `get_project_state` round-trip 5 times after a warm-up.**

In the chat UI: type "give me a project summary" five times. Note the elapsed time printed in `[Studio AI] get_project_state` log lines (FL Script Output window) and the chat UI.

**Pass: median <12 s, max <16 s.** Fail: file a follow-up to either reduce routing scope or default `include_routing` to false.

- [ ] **Step 3: Run the §11.4 checklist** (12 steps):

1. Performance baseline (above) ✓
2. Empty project: <500 ms, capabilities show all true.
3. `include_routing: false`: drops to <5 s on the heavy project.
4. FL 21 (older): graceful degradation; no errors; routes_to lacks levels.
5. FL <20.7: `FL_VERSION_UNSUPPORTED`.
6. `get_mixer_chain(0)` works; `get_mixer_chain(200)` returns INVALID_TRACK_INDEX.
7. `get_mixer_plugin_params` on Fruity Parametric EQ 2: <200 ms.
8. `get_mixer_plugin_params` on Serum: truncated MAX_PARAMS at 64.
9. `get_channel_plugin_params` on Sampler with no instrument: INVALID_TARGET.
10. `get_channel_plugin_params` on Sytrus: full dump.
11. Anti-refetch test: ask AI to organize, agree to plan, watch logs — only ONE `get_project_state` call before `apply_organization_plan`.
12. Payload size: 30–100 KB on heavy project.
13. (Non-blocking) Windows datapoint when available.

- [ ] **Step 4: Document results in the smoke-test thread.**

Add a new "Smoke Test Results" section at the bottom of the spec:

```bash
# Edit docs/superpowers/specs/2026-05-07-bridge-tier2-introspection-design.md
# Append after the appendix:

## 17. Smoke Test Results (YYYY-MM-DD)

**Environment**
- FL Studio version: <fill in>
- Plugin build SHA: <fill in>
- Test project: 40 channels / 60 inserts / 30 patterns / 30 playlist tracks

**Performance baseline (5 runs)**
- Run 1: X.X s
- Run 2: X.X s
- Run 3: X.X s
- Run 4: X.X s
- Run 5: X.X s
- Median: X.X s
- Max: X.X s
- VERDICT: PASS / FAIL

**Checklist results**
- (1) Perf: <result>
- (2) Empty project: <result>
- ...
```

- [ ] **Step 5: Commit smoke results to the spec.**

```bash
git add docs/superpowers/specs/2026-05-07-bridge-tier2-introspection-design.md
git commit -m "docs(specs): tier 2 introspection smoke-test results

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (writing-plans skill output)

**Spec coverage check:**
- §1 floor: covered by Task 5 + 9.
- §4.1 extended `get_project_state`: Tasks 9, 10.
- §4.2 `get_mixer_chain`: Task 11.
- §4.3 split plugin params: Task 12.
- §4.4 `get_mixer_eq`: Task 13.
- §4.5 no public `get_capabilities`: Task 5 (internal only) + Task 18 (snapshot exclusion).
- §5 capability probe: Task 5.
- §6 perf budget + truncation: Task 10.
- §7 implementation: Tasks 5–14.
- §8 web tools: Tasks 15–17.
- §9 system prompt: Task 19.
- §10 error handling: distributed across Task 5, 9, 11, 12.
- §11.1 bridge tests: Tasks 5–13 each include their tests.
- §11.2 web tool tests: Task 18.
- §11.3 evals: Task 20.
- §11.4 manual smoke: Task 21.
- §12 implementation order: matched.
- §13 TS migration: Tasks 2–4.
- §14 risks: addressed by tests in Tasks 5–13 and merge gate Task 21.
- §15 vault docs: deferred (separate task — invoke `vault-maintain` after implementation).
- §16 downstream: out of scope for this plan.

**Placeholder scan:** No "TBD", "implement later", or "similar to Task N" instances. Every step has actionable code or commands.

**Type consistency:** `ChannelPluginInfo`, `MixerRoute`, `EnhancedProjectState`, `INTROSPECT_HANDLERS`, `_probe_capabilities`, `_dump_plugin_params`, `MAX_*` constants — used consistently.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-07-bridge-tier2-introspection.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
