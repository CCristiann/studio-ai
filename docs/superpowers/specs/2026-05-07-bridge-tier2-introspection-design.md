# Bridge Tier 2: Project Introspection — Design Spec

**Date:** 2026-05-07
**Status:** Draft v2 — review-revised
**Scope:** Add structural introspection (plugin identity, mixer routing topology, send levels, mixer effect chains, EQ values, pattern length, selection state) to the FL Studio bridge so the agent can read enough context to organize messy projects intelligently. Read-only — no new write paths.

**Supported FL Studio version floor:** **FL 20.7+** (API ≥ 19). Older FL versions are not supported because `channels.getChannelType` (API v19) is required core for plugin-identity inference. Below the floor, the bridge returns a single `{success: false, error: "FL_VERSION_UNSUPPORTED", ...}` from `get_project_state` and refuses to enumerate.

---

## 1. Goals

- **Give the agent enough structural context to behave intelligently on a typical messy professional project** (40–80 used mixer inserts, 20–40 channels, 30+ patterns) without exceeding the relay timeout or burning excessive AI context window.
- **Surface plugin identity per channel and per mixer slot** — the single highest-leverage piece of context for role inference (drums vs bass vs lead vs vocal vs FX).
- **Surface the full mixer signal-flow graph** (routing topology + send levels) so the agent can detect what's already grouped, what's straight-to-Master, and what sends are non-obvious.
- **Stay within the existing performance and reliability envelope** — 30 s relay timeout, 20 s plugin pipe timeout, partial-success semantics, graceful degradation when running on older FL versions that lack newer getters.

## 2. Non-goals

Explicitly **out of scope** for this spec — each is its own future track:

- **Note content reading** (piano-roll notes, melodies, chord progressions). Belongs to a separate `.flp` parsing or piano-roll-script track.
- **Playlist clip placement on the timeline.** Same — `.flp` parser only.
- **Automation clip target/points.** Same.
- **Sample file paths.** Not exposed to controller scripts; needs `.flp`.
- **Plugin parameter dumps for every plugin on every track.** Performance prohibitive (see §6.2). On-demand drill-down only.
- **Project key inference.** Requires note content.
- **New write commands.** This is a read-only expansion.
- **Multi-agent orchestration / agent topology changes.** Deferred until the agent is observed running with richer context.
- **`.flp` file parsing / PyFLP integration.** Separate spec, blocked on a hands-on PyFLP spike against FL 2024+ projects.
- **Inference layer features** (drum-bus detection, lead inference, duplicate-plugin detection, orphan detection). Each is its own follow-up; this spec only delivers the raw signals.

## 3. Why this matters now

The current `get_project_state` handler returns names/colors/volumes/pans for channels, mixer tracks, playlist tracks, and patterns. That's enough to *rename* and *recolor* — but not enough to *reason*. To organize a messy project the agent needs to know:

- "Channel 7 is a Sytrus" → likely a synth → likely melody/lead/pad role.
- "Channel 3 is a Sampler with a kick-drum-shaped step pattern" → drums.
- "Inserts 5–12 all route to Insert 13" → that's already a sub-bus the user built.
- "Insert 47 has FabFilter Pro-Q, Pro-C, Pro-DS, and a reverb send to Insert 88" → vocal chain.
- "Insert 22 has *two* Fruity Parametric EQ instances back-to-back" → duplicate processing to flag.

None of those are inferable from current bridge data. All become trivial with the additions in this spec.

## 4. New READ commands

Five new commands. All read-only. All registered in a new `bridge/fl_studio/handlers_introspect.py` module that imports lazily from FL's runtime modules.

| Tool | Domain module (web) | Purpose | Default cost |
|---|---|---|---|
| Extends `get_project_state(include_routing?)` | `project.ts` | Adds `plugin`, `slot_count`, `routes_to[]` per entity, plus `selection`, `capabilities` | 2–8 s realistic; routing is the dominant cost — see §6 |
| `get_mixer_chain(track_index)` | `mixer.ts` | Effect-slot enumeration for one mixer track (slot index → plugin name + color) | ~50 ms |
| `get_mixer_plugin_params(track_index, slot_index, max_params?)` | `mixer.ts` | Generic plugin parameter dump for one mixer-slot plugin | 100–500 ms (with 2 s wall-clock guard for hung plugins) |
| `get_channel_plugin_params(channel_index, max_params?)` | `channels.ts` | Generic plugin parameter dump for one channel-rack plugin | 100–500 ms (same guard) |
| `get_mixer_eq(track_index)` | `mixer.ts` | 3-band EQ values for one mixer track (FL 2024+) | <10 ms |

The first item — extending `get_project_state` — is the load-bearing change. The rest are on-demand drill-downs.

**Why two `*_plugin_params` tools instead of one with a magic `slot_index = -1`:** mixer-slot plugins and channel-rack plugins address differently in FL's API and behave differently for sample-based channels (where `plugins.isValid(channel, -1)` returns false). Split tools make the schema unambiguous to the model and avoid an empty-response trap on Sampler channels.

**Why no standalone `get_capabilities` tool:** the same `capabilities` object ships inline with every `get_project_state` response. Exposing a separate tool wastes a model-selection slot on something never called in isolation. The bridge handler still exists internally for the probe.

### 4.1 Extended `get_project_state`

**New optional input parameter:**

```ts
inputSchema: z.object({
  include_routing: z.boolean().optional().default(true)
    .describe("Include per-track outbound routing graph. Default true. Set false on cold-start probes or huge projects to skip the O(retained × 127) sweep."),
})
```

The schema gains new fields and **changes the shape of `channels[].plugin`** from `string` (which the bridge never actually emitted but the TS type defined) to a structured object. This is a cross-package type migration — see §15 for the full migration plan.

```typescript
{
  // unchanged
  bpm: number,
  project_name: string,
  playing: boolean,

  // unchanged but ENRICHED — see new fields per item below
  channels: Array<{
    index: number,                  // 0-indexed
    name: string,
    color: number,                  // 24-bit RGB
    volume: number,
    pan: number,
    enabled: boolean,
    insert: number,                 // mixer routing target

    // NEW
    plugin: {
      name: string,                 // e.g. "Sytrus", "FLEX", "Fruity Kick", "Serum"
      type: number,                 // FL channel type code
      type_label: string,           // "sampler" | "hybrid" | "vst" | "automation" | "layer" | "midi_out" | "unknown"
    } | null,                       // null when channels.getChannelType raises (rare)
  }>,

  mixer_tracks: Array<{
    index: number,                  // 0-indexed (0=Master)
    name: string,
    color: number,
    volume: number,
    pan: number,
    muted: boolean,

    // NEW
    slot_count: number,             // # of loaded effect slots (0..10)
    routes_to: Array<{              // outbound sends (excluding the implicit Master route)
      to_index: number,
      level?: number,               // FL 2024+ only; 0..1 normalized; omitted on older FL
    }>,
  }>,

  playlist_tracks: Array<{ index: number, name: string, color: number }>,
  patterns: Array<{
    index: number,
    name: string,
    color: number,
    length_beats?: number,          // NEW — omitted if patterns.getPatternLength raises
  }>,

  // NEW — what the user is currently looking at in FL.
  // CAVEAT: read sequentially without locking. The user may click between
  // reads, so the three values are individually current but not necessarily a
  // coherent point-in-time snapshot. Same applies to the project state at
  // large — the response is a non-transactional sweep, not a frozen view.
  selection: {
    channel_index: number | null,
    pattern_index: number | null,
    mixer_track_index: number | null,
  },

  // NEW — server-side timestamp of when the sweep started, for client-side
  // staleness checks if needed.
  snapshot_at: number,                // unix epoch seconds

  // NEW — when truncation guards fire, the agent must surface this honestly.
  truncated_sections?: Array<"channels" | "mixer_tracks" | "patterns" | "playlist_tracks" | "routing">,

  // NEW — gating info; lets the AI know which features are available
  capabilities: {
    fl_version: string,             // e.g. "21.2.3"
    api_version: number,            // e.g. 33
    has_send_levels: boolean,       // mixer.getRouteToLevel  (api ≥ 36, FL 2024+)
    has_eq_getters: boolean,        // mixer.getEqGain/Frequency/Bandwidth  (api ≥ 35)
    has_save_undo: boolean,         // general.saveUndo  (already used by apply)
    has_pattern_length: boolean,    // patterns.getPatternLength
  },
}
```

**Filtering rules** (preserved from current implementation):
- Mixer tracks: include Master (0) always; otherwise include only tracks with custom name **OR** custom color **OR** ≥1 loaded effect slot **OR** ≥1 outbound send. The new `slot_count > 0` and `len(routes_to) > 0` conditions catch tracks the user has set up structurally even without renaming them — important for messy real-world projects.
- Playlist tracks: include only tracks with custom name OR custom color (unchanged).
- Patterns: include only patterns with custom name OR custom color OR `length_beats > 0` and not the engine default (unchanged).
- Channels: always all (unchanged).

**Indexing conventions** (preserved): channel rack and mixer 0-indexed; playlist and patterns 1-indexed.

### 4.2 `get_mixer_chain(track_index)`

On-demand drill-down for one mixer track's effect chain. Used when the agent wants to see what plugins are on the vocal chain, drum bus, master, etc.

```ts
inputSchema: z.object({
  index: z.number().int().min(0).max(126),
})
```

Response:

```ts
// Out-of-range index:
{ success: false, error: "INVALID_TRACK_INDEX", track_count: number }

// Valid:
{
  index: number,
  slots_enabled: boolean,           // track-level: mixer.isTrackSlotsEnabled(track) — applies to ALL loaded slots
  slots: Array<{
    slot_index: number,             // 0..9
    plugin_name: string,
    color?: number,                 // FL 32+ only via mixer.getSlotColor; omitted otherwise
  }>,
}
```

**No per-slot `enabled` field.** FL's Python API exposes `mixer.isTrackSlotsEnabled(track)` (per-track) but no per-slot getter. We surface the track-level state once as `slots_enabled` rather than fabricate a `true` for every slot. The agent is told in the system prompt that `slots_enabled: false` means none of the listed plugins are currently processing.

Implementation: validate `track_index < mixer.trackCount()` and return `{success: false, error: "INVALID_TRACK_INDEX"}` if out of range. Otherwise iterate `slot in 0..9`, call `plugins.isValid(track_index, slot)`, on valid slots call `plugins.getPluginName`. Use `continue` (not `break`) on per-slot exceptions so a single misbehaving slot doesn't drop later slots. ~10–20 calls per track.

### 4.3 `get_mixer_plugin_params` and `get_channel_plugin_params`

Generic plugin parameter dumps. Use cases: detect duplicate EQs (same params), surface the main controls of a plugin to the user. Opt-in because some VSTs report 4000+ params.

```ts
// Mixer-slot variant
get_mixer_plugin_params: {
  inputSchema: z.object({
    track_index: z.number().int().min(0).max(126),
    slot_index: z.number().int().min(0).max(9),
    max_params: z.number().int().min(1).max(500).optional().default(64),
  })
}

// Channel-rack variant
get_channel_plugin_params: {
  inputSchema: z.object({
    channel_index: z.number().int().min(0).max(999),
    max_params: z.number().int().min(1).max(500).optional().default(64),
  })
}
```

Response (same shape for both):

```ts
{
  // Out-of-range or invalid slot:
  // { success: false, error: "INVALID_TARGET" }

  // Wall-clock budget exceeded mid-iteration (hung-plugin guard):
  // returned with elapsed_ms > 2000:
  // { ..., truncated: true, truncated_reason: "TIME_BUDGET", params: [partial] }

  plugin_name: string,
  param_count: number,              // full count from FL
  returned_count: number,           // params actually returned
  truncated: boolean,               // true if param_count > returned_count for any reason
  truncated_reason?: "MAX_PARAMS" | "TIME_BUDGET",
  elapsed_ms: number,
  params: Array<{
    index: number,
    name: string,
    value: number,                  // 0..1 normalized
    value_string?: string,          // FL's display string; not all plugins return one
  }>,
}
```

**Performance protection (the hung-plugin guard is the critical part):**

- Soft cap at `max_params` (default 64; hard ceiling 500).
- **Wall-clock budget of 2 s inside the iteration.** Some VSTs (older Waves, some IK Multimedia) block in `getParamValueString` while waiting on a closed plugin GUI thread. After every 8 params the loop checks `time.time() - start > 2.0`; if exceeded, it returns whatever was collected with `truncated: true, truncated_reason: "TIME_BUDGET"`. This prevents a single hung plugin from burning the 20 s pipe timeout.
- Each call wrapped in try/except; individual param failures don't abort the loop.
- The AI's tool description tells it to use these tools sparingly and only when the user's request specifically demands param introspection.

### 4.4 `get_mixer_eq(track_index)`

```ts
inputSchema: z.object({
  index: z.number().int().min(0).max(126),
})
```

Response:

```ts
{
  index: number,
  available: boolean,               // false on FL pre-2024; bands omitted
  bands?: {
    low:  { gain: number, freq: number, bw: number },  // all 0..1 normalized
    mid:  { gain: number, freq: number, bw: number },
    high: { gain: number, freq: number, bw: number },
  },
}
```

Returns `available: false` cleanly when `mixer.getEqGain` is absent (i.e. older FL). The AI is told to check `available` before using the values.

### 4.5 (removed) `get_capabilities` is not exposed as a public tool

The capabilities object ships inline with every `get_project_state` response. The bridge handler still exists for the probe and for the bridge's own gating logic, but is not registered as an AI tool — exposing it would waste a model-selection slot on something never independently called.

## 5. FL version capability detection

The bridge probes once on first call and caches the result. **The version floor is FL 20.7+ (API ≥ 19).** Below the floor the bridge refuses to enumerate (see §1).

The probe is exhaustive — it gates every FL function the new code calls, not just the FL 2024+ additions, because (a) the cost of `hasattr` is negligible and (b) the bridge has historically broken in production when an assumed-present function went missing on a particular FL build.

```python
_CAPS = None  # module-level cache; permissive defaults if probe itself fails


def _probe_capabilities():
    """Probe once. On any failure, return permissive defaults rather than
    raising — the bridge stays up and the agent sees an honest 'minimal
    capabilities' view via the response.
    """
    global _CAPS
    if _CAPS is not None and _CAPS.get("api_version", 0) > 0:
        return _CAPS  # only re-probe if previous probe failed (api_version=0)

    fl_version = "unknown"
    api_version = 0
    has = {
        # Required core (floor enforcement) — if any of these are missing we
        # surface FL_VERSION_UNSUPPORTED in the project-state response.
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
        for key in has:
            mod_name, fn_name = key.split(".")
            mod = {"channels": channels, "mixer": mixer, "patterns": patterns,
                   "plugins": plugins, "general": general, "ui": ui}[mod_name]
            has[key] = hasattr(mod, fn_name)
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
```

All new readers consult `_CAPS` before calling version-gated functions. **No code path raises `AttributeError` from a missing FL function.** When `_has_floor_core` is false, the project-state handler short-circuits to `FL_VERSION_UNSUPPORTED`.

This is the same pattern used by the existing `apply_organization_plan` for `general.saveUndo` (`undo_grouped` flag), generalized.

## 6. Performance budget

Three budgets matter: relay round-trip (30 s relay timeout), plugin pipe IPC (20 s plugin pipe timeout — the actual ceiling), and AI context (response payload must stay reasonable so it doesn't dominate the model's context window).

### 6.1 Honest time accounting

**Per-call cost is dominated by FL native dispatch, not Python loop overhead.** Empirical baseline from the existing `get_project_state` on macOS pipe IPC:

- ~0.5–2 ms per FL getter call inside FL's runtime.
- ~50–500 ms IPC round-trip overhead (pipe write + plugin read + base64 framing on Windows; pipe is faster on macOS).
- ~10–50 ms JSON serialization for a 25–100 KB payload.
- Cold-start latency on first message after a WebSocket reconnect is significantly higher (we already raised `RELAY_REQUEST_TIMEOUT_SECONDS` from 5 → 30 s for this reason — see [bulk-apply spec §13](./2026-04-15-organize-bulk-and-tool-registry-design.md#13-smoke-test-results-2026-04-16)).

The single biggest cost is the routing sweep: `mixer.getRouteSendActive(src, dst)` is per-pair, with no batch API. For each retained mixer track we sweep all 127 destinations. This is `O(retained_tracks × 127)`, not `O(retained_tracks)`.

| Section | Calls | Realistic cost (in-FL) |
|---|---|---|
| Capabilities probe (one-time, cached) | ~14 hasattr | <5 ms |
| Project metadata | ~5 | <10 ms |
| Channels (40 ch × 7 calls + plugin) = 320 | 320 | ~0.3 s |
| Mixer (60 retained × ~7 base + slot_count probe of 10) | 1,020 | ~1.0 s |
| **Mixer routing sweep** (60 retained × 127 dst, with active routes triggering 1 extra getRouteToLevel each) | **~7,800** | **~5–8 s** |
| Playlist (500 × 2 + theme sample) | 1,005 | ~1.0 s |
| Patterns (999 × 4 + theme sample) | 4,001 | ~3.0 s |
| **Realistic total** | **~14,000** | **~10–13 s** |

That's tight against the 20 s pipe timeout. **The routing sweep is the dominant cost.**

**This spec REQUIRES a measured baseline before merge** — see §11.4 step 1. The numbers above are sanity-checked extrapolations, not measurements. The merge gate is: realistic-case `get_project_state` (40 channels, 60 retained inserts, 30 patterns, 30 playlist tracks) measured on real FL Studio macOS completes in **under 12 s including IPC**.

### 6.2 Hard guardrails (truncation envelope)

Mirroring the bulk-apply `PLAN_TOO_LARGE` pattern, the introspection handler enforces hard caps to keep worst-case behavior bounded:

```python
MAX_CHANNELS_INTROSPECTED         = 256
MAX_RETAINED_INSERTS              = 128
MAX_RETAINED_INSERTS_FOR_ROUTING  = 100   # routing-sweep guard; below cap = full graph
MAX_PATTERNS                      = 256
MAX_PLAYLIST_TRACKS               = 256
```

When any cap is hit:
- The entity list is truncated at the cap.
- `truncated_sections` includes the section name in the response (see schema in §4.1).
- The agent's system prompt instructs it to surface this honestly to the user ("Your project has 600 patterns; I can only see the first 256 — let me know if a specific pattern isn't visible").

When `len(retained_inserts) > MAX_RETAINED_INSERTS_FOR_ROUTING`:
- Routing is enumerated for the **first** `MAX_RETAINED_INSERTS_FOR_ROUTING` retained inserts (sorted ascending by `index`). Tracks beyond the cutoff have `routes_to: []` regardless of actual routing state.
- The response includes `routing_swept_through: <last_swept_index>` so the agent knows where the partial graph ends.
- `truncated_sections` includes `"routing"`.
- Rationale: a partial-but-bounded graph is strictly more useful than no graph. Lower-indexed tracks are usually source channels (drums, instruments) and contain most of the signal-flow signal; higher-indexed tracks are typically destinations and sub-busses, which the agent can probe individually with `get_mixer_chain` if needed.
- The agent is told via the system prompt: when `truncated_sections` includes `"routing"`, signal flow inference is partial for tracks above `routing_swept_through`; surface this to the user.

When `include_routing: false` is passed:
- Routing sweep is skipped entirely. `routes_to: []` for every track.
- This is the explicit escape hatch for cold-start probes or initial summaries.

### 6.3 What we explicitly DON'T enumerate by default

- **Plugin parameters across every plugin on every slot** would be `60 inserts × ~5 loaded slots × ~50 params × 3 calls = 45,000 calls = 45 s` — over budget. Hence `get_mixer_plugin_params` / `get_channel_plugin_params` are on-demand, one plugin at a time, with `max_params` cap and 2 s wall-clock guard.
- **Effect chain enumeration on every mixer track** is `125 inserts × 10 slots × 2 calls = 2,500 calls`. We mitigate by including only `slot_count` in the default project state (1 isValid sweep per insert = `60 × 10 = 600` calls = ~0.6 s, already counted above) and pushing per-slot detail to `get_mixer_chain`.

### 6.4 Payload-size budget

Worst-case extended `get_project_state` (after caps):
- 256 channels × ~280 B per channel ≈ 72 KB
- 128 used inserts × ~340 B per insert (incl. routes_to up to 5) ≈ 44 KB
- 256 playlist + 256 patterns × ~80 B ≈ 41 KB
- **Worst-case payload (truncated) ≈ 160 KB.** Sits within Vercel AI SDK tool-result limits.

**Realistic case** (filtered, default-named removed) is ~15–35 KB. Fine.

### 6.5 Logging guardrails (preserved)

- Every loop has `try/except` around the FL call so one bad index doesn't abort the sweep (existing pattern in `_cmd_get_project_state`).
- Bridge logs per-section timing with `!! SLOW` (>10 s) and `!!! NEAR-TIMEOUT` (>18 s) markers, mirroring the existing pattern. New sections (channels-with-plugin, mixer-with-routing) get their own timing lines so we can identify regressions.

## 7. Bridge implementation

### 7.1 New file: `bridge/fl_studio/handlers_introspect.py`

Mirror the structure of `handlers_organize.py` and `handlers_bulk.py`. Exports an `INTROSPECT_HANDLERS` dict registered in `device_studio_ai.py`.

The `_CAPS` module-level cache and `_probe_capabilities` are defined exactly once (in §5 above — that's the authoritative implementation, including the import-failure permissive-default path and the re-probe-on-`api_version=0` behavior). Don't re-implement here.

Channel-type label map (codes are stable across FL versions):

```python
_CHANNEL_TYPE_LABELS = {
    0: "sampler",
    1: "hybrid",   # legacy generator
    2: "vst",
    3: "midi_out",
    4: "automation",
    5: "layer",
}


def _cmd_get_capabilities(_params):
    """Internal probe handler. Not exposed as an AI tool — see §4.5."""
    return _probe_capabilities()
```

Then the enriched introspection helpers:

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
        # plugins.getPluginName takes (channelOrTrack, slot=-1 for channel rack).
        plugin_name = plugins.getPluginName(idx, -1) or ""
    except Exception:
        plugin_name = ""
    return {
        "name":       plugin_name,
        "type":       type_code,
        "type_label": _CHANNEL_TYPE_LABELS.get(type_code, "unknown"),
    }


def _mixer_routes(src):
    """Return list of {to_index, level?} for outbound sends from src.

    Excludes self-route. Includes Master only if explicitly enabled (FL
    auto-routes everything to Master implicitly; we surface explicit
    routes the user has set up).
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


def _mixer_slot_count(track):
    """Return # of loaded effect slots on `track` (0..10).

    Uses `continue` (not `break`) on per-slot exceptions: a single misbehaving
    slot must not silently undercount the rest of the chain.
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
```

The enriched `get_project_state` calls `_channel_plugin(i)` for every channel, `_mixer_slot_count(i)` and `_mixer_routes(i)` for every retained mixer track, and emits the new fields. Pattern length is added when `_CAPS["has_pattern_length"]` is true.

The selection block is cheap:

```python
def _selection():
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

### 7.2 `_cmd_get_mixer_chain`

```python
def _cmd_get_mixer_chain(params):
    import plugins
    import mixer
    track = int((params or {}).get("index", 0))
    slots = []
    has_slot_color = hasattr(mixer, "getSlotColor")
    for slot in range(10):
        try:
            if not bool(plugins.isValid(track, slot)):
                continue
            entry = {
                "slot_index": slot,
                "plugin_name": plugins.getPluginName(track, slot) or "",
                "enabled": True,  # see §10 caveat
            }
            if has_slot_color:
                try:
                    entry["color"] = int(mixer.getSlotColor(track, slot)) & 0xFFFFFF
                except Exception:
                    pass
            slots.append(entry)
        except Exception:
            continue
    return {"index": track, "slots": slots}
```

### 7.3 `_cmd_get_mixer_plugin_params` and `_cmd_get_channel_plugin_params`

Both handlers share an internal `_dump_plugin_params(addr_args, max_params)` helper. Two registered actions, one implementation.

```python
import time

PARAM_TIME_BUDGET_S = 2.0
PARAM_TIME_CHECK_EVERY = 8


def _dump_plugin_params(track_or_channel, slot, max_params):
    """Dump up to `max_params` params for the (track,slot) target.

    `slot=-1` for channel-rack plugins. Wall-clock budget of PARAM_TIME_BUDGET_S
    protects against UI-thread-hung VSTs. Returns the response shape from §4.3.
    """
    import plugins
    start = time.time()

    if not plugins.isValid(track_or_channel, slot):
        return {"success": False, "error": "INVALID_TARGET"}

    name = plugins.getPluginName(track_or_channel, slot) or ""
    try:
        full_count = int(plugins.getParamCount(track_or_channel, slot))
    except Exception:
        full_count = 0

    n = min(full_count, max_params)
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
                "name": plugins.getParamName(i, track_or_channel, slot) or "",
                "value": round(float(plugins.getParamValue(i, track_or_channel, slot)), 4),
            }
            try:
                vs = plugins.getParamValueString(i, track_or_channel, slot)
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
    if "track_index" not in result and result.get("success") is None:
        result["track_index"] = track
        result["slot_index"]  = slot
    return result


def _cmd_get_channel_plugin_params(params):
    channel = int((params or {}).get("channel_index", 0))
    max_params = max(1, min(500, int((params or {}).get("max_params", 64))))
    result = _dump_plugin_params(channel, -1, max_params)
    if "channel_index" not in result and result.get("success") is None:
        result["channel_index"] = channel
    return result
```

### 7.4 `_cmd_get_mixer_eq`

```python
def _cmd_get_mixer_eq(params):
    import mixer
    caps = _probe_capabilities()
    track = int((params or {}).get("index", 0))
    if not caps["has_eq_getters"]:
        return {"index": track, "available": False}
    bands = {}
    for band_name, band_idx in (("low", 0), ("mid", 1), ("high", 2)):
        try:
            bands[band_name] = {
                "gain": round(float(mixer.getEqGain(track, band_idx)), 4),
                "freq": round(float(mixer.getEqFrequency(track, band_idx)), 4),
                "bw":   round(float(mixer.getEqBandwidth(track, band_idx)), 4),
            }
        except Exception:
            bands[band_name] = {"gain": 0.5, "freq": 0.5, "bw": 0.5}
    return {"index": track, "available": True, "bands": bands}
```

### 7.5 Wiring in `device_studio_ai.py`

```python
from handlers_introspect import INTROSPECT_HANDLERS
# ...
_HANDLERS = {
    # existing entries...
    **ORGANIZE_HANDLERS,
    **BULK_HANDLERS,
    **INTROSPECT_HANDLERS,   # NEW
}
```

The enriched `get_project_state` overrides the existing `get_project_state` key in `INTROSPECT_HANDLERS` (Python dict-merge order). The bridge keeps the older `_cmd_get_state` alias of `get_state` as a fallback so any non-AI debug clients keep working.

## 8. Web tool registry additions

Following the `_shared.relayTool` pattern in [apps/web/src/lib/ai/tools/](../../apps/web/src/lib/ai/tools/).

### 8.1 Updated `apps/web/src/lib/ai/tools/project.ts`

```ts
export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description: "Snapshot of the FL Studio project: BPM, channels (with plugin identity), mixer tracks (with effect-slot counts and routing graph), playlist tracks, patterns (with length), current selection, and FL capabilities. Call ONCE at the start of any organize task — do NOT re-call within the same turn after the user has agreed to a plan; the user agreed to what you summarized, not to a re-fetch.",
      inputSchema: z.object({
        include_routing: z.boolean().optional().default(true)
          .describe("Include per-mixer-track outbound routing graph. Default true. Pass false for a fast cold-start summary, or when a prior call returned truncated_sections containing 'routing'."),
      }),
      toRelay: ({ include_routing }) => ({
        action: "get_project_state",
        params: { include_routing },
      }),
    }),

    undo: relayTool(userId, { /* unchanged */ }),
  };
}
```

`get_capabilities` is intentionally not exposed (capabilities ship inline with `get_project_state`).

### 8.2 Updated `apps/web/src/lib/ai/tools/mixer.ts`

```ts
get_mixer_chain: relayTool(userId, {
  description: "List the effect-plugin chain on one mixer track (slot index → plugin name + color, plus a track-level slots_enabled flag). Use this to inspect signal chains — the vocal chain, drum-bus processing, mastering chain, etc. Returns { success: false, error: 'INVALID_TRACK_INDEX' } if the index is out of range.",
  inputSchema: z.object({
    index: MX_INDEX,
  }),
  toRelay: ({ index }) => ({ action: "get_mixer_chain", params: { index } }),
}),

get_mixer_plugin_params: relayTool(userId, {
  description: "Dump parameter values for one plugin in a mixer slot. Use sparingly — large VSTs report hundreds of params. Default cap is 64; raise max_params only when you specifically need a deeper read. May return truncated_reason: 'TIME_BUDGET' if the plugin's GUI thread is hung; surface that honestly to the user.",
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
  description: "Read the 3-band EQ values (low/mid/high) for one mixer track. Returns { available: false } on FL versions older than 2024 — check before using values.",
  inputSchema: z.object({ index: MX_INDEX }),
  toRelay: ({ index }) => ({ action: "get_mixer_eq", params: { index } }),
}),
```

### 8.3 Updated `apps/web/src/lib/ai/tools/channels.ts`

Add the channel-rack variant:

```ts
get_channel_plugin_params: relayTool(userId, {
  description: "Dump parameter values for the plugin loaded on one channel rack entry. Same caveats as get_mixer_plugin_params. Returns { success: false, error: 'INVALID_TARGET' } if the channel has no plugin (e.g. a Sampler channel with no instrument).",
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

`patterns.ts`, `playlist.ts`, `transport.ts`, `organize.ts` remain unchanged.

## 9. System-prompt update

Add the following section in [apps/web/src/lib/ai/system-prompt.ts](../../apps/web/src/lib/ai/system-prompt.ts) — placed after the existing "Tool selection rules" block.

```text
# Reading project context

`get_project_state` returns rich structural context. Use it once at the start of any organize task. **Do NOT call get_project_state twice within the same conversation turn:** if you've shown the user a summary built from one snapshot and they agreed to act, re-fetching produces a slightly different snapshot (the user may have clicked something) and the plan you apply may not match what the user agreed to.

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

## 10. Error handling & edge cases

| Failure mode | Behavior |
|---|---|
| FL function raises mid-iteration | Logged; that index is skipped in the response. Sweep continues. |
| FL function is missing on this version | Probed once via capabilities; gated calls are `if has_X:`. Response omits the absent field rather than raising. |
| `plugins.getPluginName` returns `None` or empty string for a loaded slot | `plugin_name: ""`. The agent treats empty string as "unknown plugin." |
| `channels.getChannelType` returns an unknown code | `type_label: "unknown"`. `type` carries the raw int for forensic logging. |
| Self-route in mixer (`getRouteSendActive(i, i)`) | Skipped. (Defensive — FL shouldn't return true here, but it cost nothing to skip.) |
| Plugin reports `param_count = 0` | `params: []`, `truncated: false`. Empty is a legitimate state. |
| `get_plugin_params` called on an invalid (track, slot) | Returns `{plugin_name: "", param_count: 0, params: []}`. The AI is told to call this only after seeing the slot via `get_mixer_chain` or `get_project_state`'s `slot_count`. |
| `get_mixer_chain` on Master (index 0) | Works — Master can have plugins. No special case. |
| Per-slot `enabled` state | FL exposes `mixer.isTrackSlotsEnabled(track)` which is per-track, not per-slot. Per-slot enable/disable is not in the public API. We default `enabled: true` per slot and document the limitation in the tool description. (No misleading data — we just can't surface this granularity.) |
| Project loaded mid-call | If FL is mid-load and a getter raises, the protective try/except handles it. The response will be sparser than usual; the AI should just call `get_project_state` again. |
| Capabilities probe itself raises | `_CAPS` is set to a permissive default (`has_X: false` for everything optional, `fl_version: "unknown"`, `api_version: 0`). The agent receives an honest "minimal capabilities" view and degrades gracefully. |

**No silent fallbacks to fabricated values.** Every uncertainty is either omitted, surfaced as `null`, or returned with an explicit boolean (`available: false`).

## 11. Testing strategy

### 11.1 Bridge unit tests (`bridge/fl_studio/tests/test_handlers_introspect.py`)

All run under the existing `conftest.py` mock-FL-modules setup.

**Capability probe:**
- `test_capabilities_probe_caches` — `_CAPS` is set once and reused on subsequent calls; the underlying `hasattr` checks happen exactly once.
- `test_capabilities_with_missing_features` — when mocked FL lacks `getRouteToLevel`, `getEqGain`, `saveUndo`, `getPatternLength`, `getSlotColor`, the probe reports `has_X: false` for each.
- `test_capabilities_with_missing_floor_core` — when mocked FL lacks `getChannelType`, `_has_floor_core` is false and `get_project_state` returns `{success: false, error: "FL_VERSION_UNSUPPORTED"}`.
- `test_probe_falls_back_when_imports_raise` — when `import mixer` raises (cold-start race), the probe returns permissive defaults (`api_version: 0`, all `has_X: false`) without propagating the exception. (Tests the `except Exception` around the imports block.)
- `test_probe_re-probes_after_failed_initial` — when first probe failed (api_version=0), the next call re-probes; when first probe succeeded, the second call uses cache.

**Project state — happy path:**
- `test_get_project_state_includes_plugin_identity` — channel entries include `plugin: {name, type, type_label}` when `getChannelType` succeeds; `null` when it raises.
- `test_get_project_state_routing_topology` — mixer entries include `routes_to: [{to_index, level?}]` matching the mocked routing matrix; `level` is omitted when `has_send_levels` is false.
- `test_get_project_state_slot_counts` — `slot_count` reflects the number of mocked-valid slots per track.
- `test_get_project_state_filtering_includes_slotted_tracks` — a mixer track with no custom name and no custom color but ≥1 loaded effect slot IS included.
- `test_get_project_state_filtering_includes_routing_sources` — a track with no name/color/slots but ≥1 outbound active send IS included.
- `test_get_project_state_pattern_length_when_available` — `length_beats` is included when `has_pattern_length`; absent otherwise.
- `test_get_project_state_includes_snapshot_at` — response includes a unix timestamp.

**Project state — guardrails:**
- `test_get_project_state_include_routing_false_skips_sweep` — when called with `include_routing: false`, `routes_to: []` for every track and `getRouteSendActive` is never called.
- `test_get_project_state_routing_truncated_at_cap` — when `len(retained_inserts) > MAX_RETAINED_INSERTS_FOR_ROUTING`, all `routes_to: []` and `truncated_sections` includes `"routing"`.
- `test_get_project_state_channels_truncated` — with 300 mock channels and `MAX_CHANNELS_INTROSPECTED=256`, response has 256 channels and `truncated_sections` includes `"channels"`.
- `test_get_project_state_patterns_truncated` — same for patterns.
- `test_get_project_state_under_500ms_synthetic_60track` — perf smoke: 60 channels + 60 mixer tracks of mocked data with full routing completes in under 500 ms in pure-Python (mocked FL calls return instantly; this calibrates Python overhead regression, not FL latency).

**Selection state:**
- `test_selection_partial` — if `mixer.trackNumber` raises, `selection.mixer_track_index` is `null` while the other two are populated.
- `test_selection_all_missing_capabilities` — if all three FL functions are absent, all three fields are `null`.

**`get_mixer_chain`:**
- `test_get_mixer_chain_skips_invalid_slots` — only valid slots appear; invalid slots are silently skipped.
- `test_get_mixer_chain_continues_past_per_slot_exception` — if slot 3 raises, slots 4-9 are still probed (regression guard for the `break` → `continue` fix).
- `test_get_mixer_chain_invalid_index` — `track_index >= mixer.trackCount()` returns `{success: false, error: "INVALID_TRACK_INDEX", track_count: N}`.
- `test_get_mixer_chain_omits_color_when_unavailable` — when `has_slot_color: false`, slot entries have no `color` field.
- `test_get_mixer_chain_includes_slots_enabled` — `slots_enabled` reflects `mixer.isTrackSlotsEnabled(track)`.

**Plugin params (both variants):**
- `test_get_mixer_plugin_params_truncates_max_params` — when `param_count > max_params`, `truncated: true, truncated_reason: "MAX_PARAMS"` and `params.length === max_params`.
- `test_get_mixer_plugin_params_truncates_time_budget` — when iteration takes >2 s (mocked sleep), returns `truncated: true, truncated_reason: "TIME_BUDGET"` with partial params.
- `test_get_mixer_plugin_params_invalid_target` — invalid (track, slot) returns `{success: false, error: "INVALID_TARGET"}`.
- `test_get_channel_plugin_params_sampler_returns_invalid_target` — for a sampler channel where `plugins.isValid(channel, -1)` returns false, response is `{success: false, error: "INVALID_TARGET"}`.
- `test_get_mixer_plugin_params_per_param_failure_continues` — if `getParamName(5)` raises, params 0-4 and 6+ are still returned.

**EQ:**
- `test_get_mixer_eq_unavailable` — when `has_eq_getters: false`, response is `{index, available: false}` with no `bands`.
- `test_get_mixer_eq_per_band_failure` — if `getEqFrequency` raises for one band, that band falls back to `{0.5, 0.5, 0.5}` and the others succeed.

### 11.2 TypeScript tool registry tests (`apps/web/src/lib/ai/tools/__tests__/`)

- `composeTools.test.ts` snapshot is updated to include `get_mixer_chain`, `get_mixer_plugin_params`, `get_channel_plugin_params`, `get_mixer_eq`. (`get_capabilities` is intentionally not in the registry — see §4.5.)
- `composeTools.test.ts` also asserts that `get_project_state`'s `inputSchema` accepts `{ include_routing: boolean }` (regression guard for the new optional flag).
- `_shared.test.ts` is unchanged.

### 11.3 AI eval (lightweight, local)

Add to the existing eval suite in `apps/web/src/lib/ai/__evals__/` (or wherever tool-selection evals live):

**Tool-selection evals** (which tool the model picks first):

| Prompt | Expected first tool |
|---|---|
| "What plugins are on the master?" | `get_mixer_chain` |
| "What's the vocal chain look like?" | `get_project_state` (then probably `find_mixer_track_by_name("vocal")`, then `get_mixer_chain`) |
| "Are there duplicate EQs anywhere?" | `get_project_state` (to find inserts), then `get_mixer_chain` per insert |
| "What kind of synth is on channel 5?" | `get_project_state` (plugin name is in the response — no follow-up needed) |

**Response-content evals** (the more important ones — assert the model actually USES the new context):

Run with a fixture project state where:
- channel[5].plugin.name = "Sytrus"
- channel[12].plugin.name = "FLEX"
- mixer[7].name = "DRUMS", inbound routes from inserts 1-6
- mixer[22] has 6 effect slots loaded

For each prompt below, assert the AI's text response (after any tool calls return) contains the listed substrings (case-insensitive):

| Prompt | Assertion (regex, case-insensitive) |
|---|---|
| "What synths am I using?" | response matches `/sytrus/i` AND `/flex/i` |
| "Where's my drum bus?" | response matches `/insert\s*7/i` OR `/drums/i` |
| "Tell me about insert 22" | response matches `/\b6\b\s*(slot|plugin|effect|insert)/i` (avoid stray "6" matches in unrelated phrasings) |

This is what proves Tier 2 actually moved the needle. Tool-selection evals alone can pass while the model still produces generic responses that ignore the new fields.

Run locally; do not block CI on it until we have recorded fixtures.

### 11.4 Manual smoke test (real FL Studio)

**This is the merge gate.** Each step has a measured pass/fail criterion.

1. **Performance baseline (mandatory before merge).** On real FL Studio macOS, build a project with 40 channels (mix of Sampler, Sytrus, FLEX, Serum), 60 retained mixer inserts (with realistic vocal chain on one, drum bus with 6 inbound routes on another), 30 named patterns, 30 colored playlist tracks. Measure end-to-end `get_project_state` (chat-message → tool-result-back) over 5 consecutive runs after warm-up. **Pass: median <12 s, max <16 s.** Fail: revisit perf budget; consider further sectioning or making routing default-off.
2. **Empty project** — FL 2024+ on macOS. Verify `get_project_state` returns under 500 ms and `capabilities.has_send_levels` and `has_eq_getters` are both true.
3. **Same heavy project, `include_routing: false`** — should drop to <5 s. Verifies the escape hatch works.
4. **FL 21 (older)** — confirm graceful degradation: response payload omits `routes_to[].level` and `length_beats`, `capabilities.has_send_levels` is false, no errors thrown.
5. **FL <20.7** — verify `get_project_state` returns `{success: false, error: "FL_VERSION_UNSUPPORTED"}` rather than crashing or producing partial data.
6. **`get_mixer_chain` on the master** — returns the master-bus plugins. **Out-of-range index** (e.g. 200) returns `{success: false, error: "INVALID_TRACK_INDEX"}`.
7. **`get_mixer_plugin_params` on a stock Fruity Parametric EQ 2** — returns named bands with sensible 0–1 values and `value_string` populated for at least the gain knobs. `elapsed_ms < 200`.
8. **`get_mixer_plugin_params` on a third-party VST with thousands of params** (Serum/Vital) — returns `truncated: true, truncated_reason: "MAX_PARAMS"`, `params.length === 64`, total round-trip under 1 s.
9. **`get_channel_plugin_params` on a Sampler channel with no plugin** — returns `{success: false, error: "INVALID_TARGET"}` (validates the split-tool design from §4.3).
10. **`get_channel_plugin_params` on a Sytrus channel** — returns full param dump.
11. **Anti-refetch behavior (manual chat test)** — ask the AI to organize the project, accept the plan, watch the network/log: it should NOT call `get_project_state` again before `apply_organization_plan`. If it does, the system prompt rule needs strengthening.
12. **Payload size on heavy project** — log the JSON size; should be 30-100 KB, never above 200 KB. If above, evaluate the `truncated_sections` logic and caps.
13. **Windows datapoint (non-blocking)** — repeat step 1 measurement on Windows once available. If the Windows median is more than 1.5× the macOS median, file a follow-up to either raise the timeout cap on Windows or split the perf budget by platform. Not a merge gate, but tracked in the rollout.

## 12. Implementation order

Each step is independently shippable and reverts cleanly to the prior step.

1. **Capabilities probe + `get_capabilities` handler.** Smallest surface; lowest risk. Lands the version-detection plumbing every later step depends on.
2. **Plugin identity per channel** in extended `get_project_state`. One new field per channel; existing consumers are unaffected (additive).
3. **Mixer routing topology + slot counts** in extended `get_project_state`. Adds the two largest new sections to the response. Verify performance on a real project before continuing.
4. **Pattern length + selection state** in extended `get_project_state`. Small adds; round it out.
5. **`get_mixer_chain` handler + tool.** Independent of the project-state extension. Useful on its own.
6. **`get_plugin_params` handler + tool.** Same.
7. **`get_mixer_eq` handler + tool.** Same.
8. **System prompt update.** Document the new context shape and selection rules. Re-run the local AI eval suite.
9. **Manual smoke test.** Real FL on macOS; verify the §11.4 checklist.
10. **Vault docs.** ADR + component update (see §14).

Ship after step 4 if pressure to deliver is high — the extended project state is the load-bearing change. Steps 5–7 are additive drill-downs.

## 13. TypeScript migration plan

The bridge response shape change for `channels[].plugin` (string → object) is a breaking change at the TypeScript layer. The bridge currently doesn't actually emit `plugin` (callers see `undefined`), so runtime behavior was already accidentally tolerant — but the new shape WILL pass an `[object Object]` to Gemini if `_shared.ts` isn't updated. This is exactly the kind of silent-degradation bug the bulk-apply spec's §13.1 documented (`scaffold_project plan drift`).

### 13.1 Files that must change

- **`packages/types/src/organize.ts:79`** — `ChannelInfo.plugin: string` → `ChannelInfo.plugin: { name: string; type: number; type_label: ChannelTypeLabel } | null`
- **`packages/types/src/organize.ts`** — add `export type ChannelTypeLabel = "sampler" | "hybrid" | "vst" | "automation" | "layer" | "midi_out" | "unknown";`
- **`packages/types/src/organize.ts`** — extend `MixerTrackInfo` with `slot_count: number; routes_to: Array<{ to_index: number; level?: number }>`
- **`packages/types/src/organize.ts`** — extend `PatternInfo` with `length_beats?: number`
- **`packages/types/src/organize.ts`** — extend `EnhancedProjectState` with `selection: {channel_index: number|null; pattern_index: number|null; mixer_track_index: number|null}`, `capabilities: {...}`, `snapshot_at: number`, `truncated_sections?: string[]`
- **`apps/web/src/lib/ai/organize/types.ts:11`** — Zod schema: `plugin: z.string()` → `plugin: z.object({...}).nullable()`
- **`apps/web/src/lib/ai/organize/_shared.ts:32`** — preserve the role-inference signal by formatting plugin name + type label together: `plugin: c.plugin ? \`${c.plugin.name} (${c.plugin.type_label})\` : "(unknown)"`. Example outputs: `"Sytrus (vst)"`, `"Sampler (sampler)"`, `"(unknown)"`. This keeps the existing string contract downstream while preserving the type information the new bridge response carries.
- **`apps/web/src/lib/ai/organize/prompts.ts`** — review references to "plugin" in the system prompt; if it instructs the model to read `c.plugin` as a string, update to read the new shape OR continue feeding the string through `projectStateToMap`'s adapter

### 13.2 Back-compat strategy

The old organize agent paths (`apps/web/src/lib/ai/organize/`) consume project state via `projectStateToMap()` in `_shared.ts`. By updating that single adapter to extract `plugin?.name` to a string, the rest of the organize agent code keeps its existing string-based contract internally. **No changes needed to** `organization-agent.ts`, `expand-plan.ts`, `colors.ts`, or `prompts.ts`.

The new chat agent (`apps/web/src/app/api/ai/execute/route.ts`) and the new bridge tools see the rich shape directly.

### 13.3 Tests for the migration

- **TS snapshot test** of `EnhancedProjectState` — run as part of the existing `composeTools.test.ts` snapshot suite. Failing snapshot prompts deliberate review.
- **TS unit test for `projectStateToMap`** — given a fixture with `plugin: { name: "Sytrus", type: 2, type_label: "vst" }`, asserts the output's `plugin` field is the string `"Sytrus (vst)"`. Also tests `plugin: { name: "Sampler", type: 0, type_label: "sampler" }` → `"Sampler (sampler)"` and `null` plugin → `"(unknown)"`.
- **`bunx tsc --noEmit`** must pass in `apps/web/` after the migration. Per [CLAUDE.md](../../CLAUDE.md), this is a precommit check anyway.

## 14. Open risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `plugins.getPluginName(idx, -1)` returns inconsistent names for VST plugins ("Serum (x64)" vs "Xfer Serum 1.35" vs "Serum") | Medium | Pass through verbatim. Plugin-name canonicalization is a separate inference-layer concern (web side), not bridge concern. Don't over-engineer at the bridge. |
| Some FL builds expose `getChannelType` codes outside the documented `0–5` range | Low | Map unknown codes to `type_label: "unknown"`, keep raw `type` int for forensic logging. |
| `mixer.getRouteToLevel` is documented FL 2024+ but actually rolled out unevenly across patch builds | Low-medium | We already gate on `hasattr`; if level reads raise individually we omit the field on a per-route basis. |
| Realistic project payload >100 KB makes the AI's reasoning slow/expensive | Low-medium | First pass is no flags. If we observe payload bloat in production, add `include_routing` / `include_slot_counts` toggles. Punt until measured. |
| `plugins.isValid` returns true on a slot that has no actual plugin (FL bug seen in some builds) | Low | `getPluginName` returns empty in this case → recorded as `plugin_name: ""`. Not silently dropped. |
| AI under-uses the new context (keeps using the old simpler tools) | Medium | System-prompt update **with worked examples** (§9) + AI eval prompts that assert on **response content**, not just tool selection (§11.3). Re-run after each prompt revision until both pass. |
| AI over-uses the plugin params tools and burns tokens | Low-medium | Tool descriptions explicitly say "use sparingly," `max_params` defaults to 64, 2 s wall-clock guard, eval prompt mix tests this. |
| AI re-calls `get_project_state` mid-turn after the user has approved a plan, causing plan-drift (the §13 analog of the bulk-apply scaffold_project drift bug) | Medium | Explicit anti-refetch rule in system prompt (§9). Smoke test step 11 verifies behavior on real chat. If the rule fails, escalate to passing a `state_token` (response hash) into apply tools and asserting consistency bridge-side. |
| TypeScript shape change for `channels[].plugin` silently degrades the existing organize agent | Medium | Migration plan in §13. Updates `projectStateToMap` adapter so the rest of the organize agent path keeps its string contract. `bunx tsc --noEmit` + new unit test for `projectStateToMap` are merge gates. |
| Routing sweep on a heavy project blows the 20 s pipe timeout | Medium | Hard cap at `MAX_RETAINED_INSERTS_FOR_ROUTING=100` triggers `truncated_sections: ["routing"]`. Escape hatch via `include_routing: false`. Merge gate is the §11.4 step 1 measurement (<12 s median). |
| Hung-plugin GUI thread blocks `get_*_plugin_params` for the full 20 s pipe timeout | Medium | 2 s wall-clock budget inside the iteration; truncates with `truncated_reason: "TIME_BUDGET"`. |
| Selection state is non-transactional (user clicks between reads) | Low | Documented in §4.1 as a caveat. AI is told never to claim a coherent point-in-time view. |
| Capability probe runs before FL fully populates its modules during boot | Low | Probe wraps imports in try/except, returns permissive defaults (`api_version: 0`). On next call, since `api_version: 0` indicates failed probe, re-probe runs. |
| `mixer.getRouteSendActive` is in the `_has_floor_core` set but its actual API-version introduction is not authoritatively documented | Low | The function is presumed long-standing (the existing organize agent uses it indirectly via FL routing assumptions). During implementation, verify against the `il-group/fl-studio-api-stubs` repo — if it turns out to be FL 21+ only, move it out of `_has_floor_core` and add a separate `has_routing` capability flag. The probe is structured to make that change one-line. |

## 15. Vault documentation (post-implementation)

After this lands, file in `obsidian-studio-ai/wiki/`:

- **ADR**: `decisions/2026-05-07-bridge-tier2-introspection.md` — captures the four-key design choices: (1) extending `get_project_state` rather than adding a parallel command, (2) plugin identity always-on, (3) routing always-on, (4) plugin params on-demand only with hard cap.
- **Concept**: `concepts/fl-capability-detection.md` — pattern of "probe once at module level, gate every version-dependent call." Reusable for future bridge work.
- **Component update**: `components/fl-studio-bridge.md` — add the new handlers and the capability-probe behavior to the documented surface.
- **Index update**: register the above in `index.md`.

Use the `vault-maintain` skill.

## 16. What this enables (downstream)

Tier 2 intentionally ships only the raw signals. The inference layer that turns those signals into intelligent organization decisions is each its own follow-up:

- **Drum-bus detector**: cluster channels by routing target; flag clusters with >3 members and rhythmic naming/plugin signals as "this is your drum bus, want to color them red?"
- **Lead-channel inferrer**: synth-type plugin (Sytrus/Serum) + monophonic step pattern + insert routing not into a sub-bus → likely lead.
- **Vocal-chain detector**: insert with ≥3 plugins, names matching {de-ess, comp, pitch, autotune, reverb, delay} → tag as vocal chain.
- **Duplicate-plugin warning**: same plugin name twice in the same `get_mixer_chain` result → flag.
- **Orphan-send detector**: send to a track that has no inbound from anywhere else and no plugins of its own → likely a forgotten reverb return / dead send.
- **"What is this project?" summary**: the agent's first action on opening becomes a one-paragraph project summary based on Tier 2 data alone (BPM + dominant plugin types + bus structure + size).

Each of those is small (~half-day to a day) on the web/agent side once Tier 2 is in production. They're the real payoff of this spec.

---

## Appendix: FL API call inventory

For reviewer reference, every FL Studio Python call introduced or relied upon by this spec:

| Call | Module | Used by | Min API version | Gated? |
|---|---|---|---|---|
| `channels.getChannelType(i)` | channels | `_channel_plugin` | v19 (FL 20+) | No (well before our floor) |
| `plugins.getPluginName(track, slot)` | plugins | `_channel_plugin`, `_cmd_get_mixer_chain`, `_cmd_get_plugin_params` | v8 | No |
| `plugins.isValid(track, slot)` | plugins | `_mixer_slot_count`, `_cmd_get_mixer_chain` | v8 | No |
| `plugins.getParamCount(track, slot)` | plugins | `_cmd_get_plugin_params` | v8 | No |
| `plugins.getParamName(i, track, slot)` | plugins | `_cmd_get_plugin_params` | v8 | No |
| `plugins.getParamValue(i, track, slot)` | plugins | `_cmd_get_plugin_params` | v8 | No |
| `plugins.getParamValueString(i, track, slot)` | plugins | `_cmd_get_plugin_params` | v8 | Try/except (some plugins don't implement) |
| `mixer.getRouteSendActive(src, dst)` | mixer | `_mixer_routes` | v? (long-standing) | No |
| `mixer.getRouteToLevel(src, dst)` | mixer | `_mixer_routes` | v36 (FL 2024) | **Yes** (`has_send_levels`) |
| `mixer.getEqGain/Frequency/Bandwidth(track, band)` | mixer | `_cmd_get_mixer_eq` | v35 (FL 2024) | **Yes** (`has_eq_getters`) |
| `mixer.getSlotColor(track, slot)` | mixer | `_cmd_get_mixer_chain` | v32 | **Yes** (per-call hasattr) |
| `mixer.trackNumber()` | mixer | `_selection` | long-standing | No |
| `patterns.getPatternLength(idx)` | patterns | extended `get_project_state` | v? | **Yes** (`has_pattern_length`) |
| `patterns.patternNumber()` | patterns | `_selection` | long-standing | No |
| `channels.selectedChannel()` | channels | `_selection` | long-standing | No |
| `general.getVersion()` | general | `_probe_capabilities` | long-standing | No |
| `ui.getVersion(0)` | ui | `_probe_capabilities` | v? | Try/except |
