# Organize Bulk Apply + Tool Registry Refactor

**Date:** 2026-04-15
**Status:** Draft — pending user review
**Scope:** Add 6 new AI tool commands focused on the organize feature (bulk apply, undo, save, name-based discovery) and refactor the AI tool definitions out of the inline `route.ts` into a per-domain registry.

---

## 1. Goals

- **Make the organize agent usable at real project scale (1–500 tracks).** Replace per-item round-trips with a single bulk-apply tool so a full project organize is one IPC hop, not hundreds.
- **Make destructive bulk operations reversible.** Wire FL Studio's native undo into the AI surface. Auto-checkpoint before applying.
- **Make conversational follow-ups natural.** Let the AI address entities by name (`"the kick"`) without re-fetching full project state.
- **Stop bloating `route.ts`.** Pull tool definitions into per-domain modules so adding tools is one file, not a 600-line patch.

## 2. Non-goals

Explicitly **out of scope** for this spec:

- MIDI / piano-roll insertion (`add_midi_notes`).
- VST plugin parameter control (`set_vst_parameter`, scan, dictionary).
- Transport polish (record, loop, metronome, snap, song position).
- Templates / saved action bundles.
- A bespoke snapshot + inverse-action undo system (FL native undo replaces this).
- Per-clip playlist control (FL Python API does not expose it).
- Dashboard UI for plan history.
- Model routing, multi-agent orchestration, conversation memory (separate future specs).

## 3. New Commands

Six new tools. Granular per-item commands stay so the AI can still do `"rename channel 3 to KICK"` without invoking the bulk path.

| Tool | Domain module | FL API path |
|---|---|---|
| `apply_organization_plan` | `organize.ts` | wraps existing setters in `general.saveUndo("Studio AI: Organize", 0)` |
| `undo` | `project.ts` | `general.undoUp()` |
| `save_project` | `project.ts` | `general.saveProject(0)` |
| `find_channel_by_name` | `channels.ts` | scan `channels.getChannelName`, rank with `difflib.get_close_matches` |
| `find_mixer_track_by_name` | `mixer.ts` | scan `mixer.getTrackName`, rank with `difflib` |
| `find_playlist_track_by_name` | `playlist.ts` | scan `playlist.getTrackName` (1-indexed), rank with `difflib` |

## 4. Tool Contracts

All schemas authored in Zod. Indexing conventions are preserved per FL Studio's API: channels and mixer 0-indexed; playlist and patterns 1-indexed.

**Range source:** FL Studio 20+ public limits, cross-checked against `mixer.trackCount()` (returns 127 in FL 20+: Master=0, Inserts=1–125, Current=126), `playlist.trackCount()` (500), `patterns.patternCount()` (999), and `channels.channelCount()` (no documented hard cap; 999 chosen as a defensive upper rail). The Zod bounds are pre-validation rails to catch obvious LLM mistakes early; the bridge re-validates against actual project state at runtime.

Hex constants used: `MAX_MIXER = 126`, `MAX_PLAYLIST = 500`, `MAX_PATTERN = 999`, `MAX_CHANNEL = 999`, `MAX_COLOR = 0xFFFFFF`, `MAX_NAME_LEN = 128`.

### 4.1 `apply_organization_plan`

```ts
inputSchema: z.object({
  channels: z.array(z.object({
    index: z.number().int().min(0).max(999),                          // 0-indexed
    name:  z.string().min(1).max(128).optional(),                     // min(1): never accidentally clear
    color: z.number().int().min(0).max(0xFFFFFF).optional(),
    insert: z.number().int().min(0).max(126).optional(),              // mixer insert routing target
  })).optional(),

  mixer_tracks: z.array(z.object({
    index: z.number().int().min(0).max(126),                          // 0=Master, 1-125=Inserts, 126=Current
    name:  z.string().min(1).max(128).optional(),
    color: z.number().int().min(0).max(0xFFFFFF).optional(),
  })).optional(),

  playlist_tracks: z.array(z.object({
    index: z.number().int().min(1).max(500),                          // 1-indexed, FL 20+ caps at 500
    name:  z.string().min(1).max(128).optional(),
    color: z.number().int().min(0).max(0xFFFFFF).optional(),
  })).optional(),

  patterns: z.array(z.object({
    index: z.number().int().min(1).max(999),                          // 1-indexed
    name:  z.string().min(1).max(128).optional(),
    color: z.number().int().min(0).max(0xFFFFFF).optional(),
  })).optional(),
})
```

**Plan size limit (5s relay timeout):**

The bulk apply runs through `apps/api` → WebSocket → bridge with a hard **5-second relay timeout** (see [Relay Service](../../../obsidian-studio-ai/wiki/components/relay-service.md)). At measured ~1ms per FL setter call:

- Worst-case full plan (500 playlist + 999 patterns + 999 channels + 126 mixer, all with rename + color) = **~5,248 calls × ~1ms = ~5.2s** — over budget.
- Realistic full plan (500 + 100 + 200 + 50 with rename + color) = **~1,700 calls = ~1.7s** — comfortable.

The bridge enforces a soft cap inside the handler: if the total item count exceeds **2,000 items**, the apply returns `{ success: false, error: "PLAN_TOO_LARGE", suggestion: "Split the plan into smaller batches." }` immediately, without touching FL. The system prompt instructs the AI to chunk plans above 2,000 items into multiple sequential applies (each in its own undo step — the user can still revert chunk-by-chunk).

**Response shape:**

```ts
{
  applied: {
    channels:        number,  // count of items where >=1 field was applied
    mixer_tracks:    number,
    playlist_tracks: number,
    patterns:        number,
  },
  errors: Array<{
    entity: "channels" | "mixer_tracks" | "playlist_tracks" | "patterns",
    index:  number,
    field:  "name" | "color" | "insert",
    message: string,
  }>,
  undo_label: string,  // matches the saveUndo label, e.g. "Studio AI: Organize"
}
```

**Semantics:**

- Each item-field is applied independently. A bad index for one item does **not** abort the rest.
- Items with no optional fields set are no-ops (counted neither as applied nor as errors).
- The whole apply registers as **a single undo step** in FL via `general.saveUndo`. One `undo` call reverts the entire batch.

### 4.2 `undo` and `save_project`

```ts
undo: {
  inputSchema: z.object({}),
  execute: () => relay("undo", {}) → { undone: true }
}

save_project: {
  inputSchema: z.object({}),
  execute: () => relay("save_project", {}) → { saved: true }
}
```

No parameters. `undo` always undoes the most recent FL action. The AI is responsible for explaining to the user what it just undid.

### 4.3 Find-by-name tools

Same shape across channels / mixer / playlist:

```ts
find_*_by_name: {
  inputSchema: z.object({
    query: z.string().min(1).max(128),
    limit: z.number().int().min(1).max(20).optional().default(5),
  }),
  execute: () => relay("find_*_by_name", { query, limit })
}
```

Response:

```ts
{
  matches: Array<{
    index: number,
    name:  string,
    score: number,  // 0.0–1.0 (hybrid: substring boost + difflib ratio)
  }>
}
```

**Scoring algorithm** (hybrid — pure `difflib.SequenceMatcher.ratio` is too strict for the dominant query case where the user types one word and expects to match longer names):

```python
def _score(query: str, name: str) -> float:
    q = query.lower()
    n = name.lower()
    # Substring match: high baseline, scaled by coverage of the candidate.
    if q in n:
        return round(0.7 + 0.3 * (len(q) / max(len(n), 1)), 3)
    # Otherwise fall back to difflib ratio.
    return round(difflib.SequenceMatcher(None, q, n).ratio(), 3)
```

Examples (cutoff 0.6):

| Query | Candidate | Pure ratio | Hybrid score | Match? |
|---|---|---|---|---|
| `kick` | `Kick` | 1.000 | 1.000 | ✓ |
| `kick` | `Kick Layer` | 0.571 | 0.820 | ✓ |
| `kick` | `Kick Layer Sub` | 0.444 | 0.786 | ✓ |
| `kick` | `Snare` | 0.000 | 0.000 | ✗ |
| `bass` | `Sub Bass 808` | 0.500 | 0.800 | ✓ |
| `vox` | `Lead Vocal` | 0.000 | 0.000 | ✗ (no substring; might warrant returning suggestions later) |

**Semantics:**

- Cutoff `0.6`. Below cutoff → omitted entirely (not returned with low score).
- Sorted by score descending, ties broken by index ascending.
- If `matches.length === 0`, the AI asks the user to clarify, never guesses.
- If `matches.length > 1` with similar scores (within `0.05` of top), the AI asks the user to disambiguate before acting.

## 5. Bridge (Python) Implementation

### 5.1 New file: `bridge/fl_studio/handlers_bulk.py`

Mirrors the structure of `handlers_organize.py`. Exports a `BULK_HANDLERS` dict registered in `device_studio_ai.py` alongside `ORGANIZE_HANDLERS`.

```python
# handlers_bulk.py — bulk apply, undo, save, find-by-name

import difflib

# Reuse the existing per-item setters from handlers_organize.
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
    total_items = sum(len(plan.get(k) or []) for k in
                      ("channels", "mixer_tracks", "playlist_tracks", "patterns"))
    if total_items > PLAN_ITEM_CAP:
        return {
            "success": False,
            "error": "PLAN_TOO_LARGE",
            "limit": PLAN_ITEM_CAP,
            "got": total_items,
            "suggestion": (
                f"Plan has {total_items} items, exceeds {PLAN_ITEM_CAP} cap. "
                "Split into smaller batches (each its own undo step)."
            ),
        }

    applied = {"channels": 0, "mixer_tracks": 0, "playlist_tracks": 0, "patterns": 0}
    errors = []
    op_count = 0

    # Group everything under a single undo entry IF saveUndo is available.
    # Older FL versions (<20) lack saveUndo; degrade gracefully.
    undo_grouped = hasattr(general, "saveUndo")
    if undo_grouped:
        try:
            general.saveUndo(UNDO_LABEL, 0)
        except Exception:
            undo_grouped = False  # FL refused; fall back

    def _apply_section(section_key, items, field_handlers):
        nonlocal op_count
        for item in items or []:
            try:
                idx = int(item["index"])
            except (KeyError, ValueError, TypeError):
                errors.append({"entity": section_key, "index": -1, "field": "index",
                               "message": "missing or invalid index"})
                continue
            touched = False
            for field, handler in field_handlers.items():
                if field in item and item[field] is not None:
                    try:
                        handler({"index": idx, field: item[field]})
                        touched = True
                        op_count += 1
                    except Exception as e:
                        errors.append({"entity": section_key, "index": idx,
                                       "field": field, "message": str(e)})
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
        "op_count": op_count,
    }


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


def _cmd_find_channel_by_name(params):
    import channels
    query = str(params.get("query", "")).strip()
    limit = int(params.get("limit", 5))
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
    query = str(params.get("query", "")).strip()
    limit = int(params.get("limit", 5))
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
    query = str(params.get("query", "")).strip()
    limit = int(params.get("limit", 5))
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


def _score(query: str, name: str) -> float:
    """Hybrid match: substring boost (covers single-word queries against
    multi-word names) + difflib SequenceMatcher fallback."""
    q = query.lower()
    n = name.lower()
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


BULK_HANDLERS = {
    "apply_organization_plan":      _cmd_apply_organization_plan,
    "undo":                         _cmd_undo,
    "save_project":                 _cmd_save_project,
    "find_channel_by_name":         _cmd_find_channel_by_name,
    "find_mixer_track_by_name":     _cmd_find_mixer_track_by_name,
    "find_playlist_track_by_name":  _cmd_find_playlist_track_by_name,
}
```

### 5.2 Wiring in `device_studio_ai.py`

```python
from handlers_organize import ORGANIZE_HANDLERS
from handlers_bulk import BULK_HANDLERS

HANDLERS = {**HANDLERS, **ORGANIZE_HANDLERS, **BULK_HANDLERS}
```

### 5.3 FL undo grouping — risk + fallback

`general.saveUndo(label, flags=0)` is documented to start a new undo entry. In practice, the behavior under a tight loop of setters is **not 100% guaranteed** to collapse into one undo step on every FL Studio version.

**Mitigation:**

1. Bridge tests verify (with mocked `general` module) that `saveUndo` is called exactly once per `apply_organization_plan` and **before** any setters fire.
2. Manual smoke test on real FL Studio (macOS first, Windows second) confirms a single `Ctrl+Z` reverts a multi-item plan.
3. **Fallback if grouping fails in practice:** track the count of operations in the bulk apply and return it; the `undo` tool gains an optional `count: number` arg so the AI can issue `undoUp()` N times. The plan envelope and AI flow stay identical; only the `undo` implementation changes.

The fallback is **not** implemented up front. We commit to the simple path and only add the count workaround if smoke testing shows we need it.

## 6. Web App (TypeScript) — Tool Registry Refactor

### 6.1 Folder structure

**Before:**

```
apps/web/src/app/api/ai/execute/route.ts   # 398 lines, ~30 inline tools
apps/web/src/lib/ai/organize/              # existing organize agent helpers
```

**After:**

```
apps/web/src/app/api/ai/execute/route.ts   # ~80 lines: composition + streamText
apps/web/src/lib/ai/
├── organize/                              # unchanged: analysis-agent, organization-agent, etc.
└── tools/
    ├── index.ts                           # composeTools(userId): assembles every tool module
    ├── _shared.ts                         # relayTool() helper, RelayError → response mapping
    ├── transport.ts                       # set_bpm, play, stop, set_pitch
    ├── channels.ts                        # rename, color, vol, pan, enabled, insert, find_by_name
    ├── mixer.ts                           # rename, color, routing, eq, find_by_name
    ├── playlist.ts                        # rename, color, find_by_name
    ├── patterns.ts                        # rename, color
    ├── project.ts                         # get_project_state, save_project, undo
    └── organize.ts                        # apply_organization_plan, organize_project, scaffold_project
```

### 6.2 The `_shared.ts` helper

Eliminates the identical try/catch boilerplate currently duplicated around every tool body in `route.ts`.

```ts
// apps/web/src/lib/ai/tools/_shared.ts
import { tool } from "ai";
import { z, ZodTypeAny } from "zod";
import { relay, RelayError } from "@/lib/relay";

export interface RelayToolDef<TInput extends ZodTypeAny> {
  description: string;
  inputSchema: TInput;
  /** Map AI tool input → relay action name + params. */
  toRelay: (input: z.infer<TInput>) => { action: string; params: unknown };
  /** Optionally transform the relay's data before returning to the AI. */
  mapResult?: (data: unknown, input: z.infer<TInput>) => unknown;
}

export function relayTool<TInput extends ZodTypeAny>(
  userId: string,
  def: RelayToolDef<TInput>
) {
  return tool({
    description: def.description,
    inputSchema: def.inputSchema,
    execute: async (input) => {
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

### 6.3 Example domain module

```ts
// apps/web/src/lib/ai/tools/project.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description: "Snapshot of the current FL Studio project: BPM, channels, mixer tracks, playlist tracks, patterns.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "get_project_state", params: {} }),
    }),

    save_project: relayTool(userId, {
      description: "Save the current FL Studio project. Use this as a checkpoint before bulk-organizing so the user can recover if they dislike the result.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "save_project", params: {} }),
    }),

    undo: relayTool(userId, {
      description: "Undo the most recent change in FL Studio (uses FL's native undo history). After applying an organization plan, this reverts the entire batch as one step.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "undo", params: {} }),
    }),
  };
}
```

### 6.4 `tools/index.ts`

```ts
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

### 6.5 `route.ts` after refactor

```ts
import { streamText, UIMessage, convertToModelMessages, stepCountIs } from "ai";
import { google } from "@ai-sdk/google";
import { auth } from "@/lib/auth";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { rateLimit } from "@/lib/rate-limit";
import { composeTools } from "@/lib/ai/tools";
import { SYSTEM_PROMPT } from "@/lib/ai/system-prompt";

async function getUserId(req: Request): Promise<string | null> { /* unchanged */ }

export async function POST(req: Request) {
  const userId = await getUserId(req);
  if (!userId) return new Response("Unauthorized", { status: 401 });

  const { success } = rateLimit(`ai:${userId}`, { limit: 20, windowMs: 60_000 });
  if (!success) return new Response("Rate limit exceeded", { status: 429 });

  const { messages }: { messages: UIMessage[] } = await req.json();

  const result = streamText({
    model: google("gemini-2.5-flash"),
    providerOptions: { google: { thinkingConfig: { thinkingBudget: 0 } } },
    system: SYSTEM_PROMPT,
    messages: await convertToModelMessages(messages),
    tools: composeTools(userId),
    stopWhen: stepCountIs(5),
  });

  return result.toUIMessageStreamResponse();
}
```

The system prompt moves to `apps/web/src/lib/ai/system-prompt.ts` so it's grep-able and editable in isolation.

## 7. Agent Flow Updates

### 7.1 Organize flow (replaces current 3-stage internal sub-agents)

```
User: "organize this project"
  ↓
AI:   get_project_state                (1 round-trip)
  ↓
AI:   produces structured plan in chat (LLM reasoning, streamed to UI)
  ↓
UI:   renders plan grouped by entity, "Apply" button
  ↓ user confirms
AI:   save_project                     (checkpoint, 1 round-trip)
AI:   apply_organization_plan(plan)    (1 round-trip; hundreds of FL calls)
  ↓
AI:   "Done. Renamed/colored 487 items. Type 'undo' to revert."
  ↓ user dislikes
User: "undo"
AI:   undo                             (1 round-trip; reverts all)
```

The current internal `runAnalysis` / `runOrganization` / `executePlan` sub-agents inside `apps/web/src/lib/ai/organize/` are **simplified**:

- `runAnalysis` is deleted; the main chat loop's call to `get_project_state` covers it.
- `runOrganization` becomes a system-prompt fragment + the `apply_organization_plan` tool. No separate `streamText` call.
- `executePlan` is deleted; the bridge's `_cmd_apply_organization_plan` does the work.
- `expand-plan.ts` may still be useful for normalizing user-tweaked plans before apply; reviewed during implementation, kept only if still load-bearing.

### 7.2 Atomic-edit flow (preserved)

```
User: "rename channel 3 to KICK"
AI:   rename_channel(3, "KICK")        (atomic, snappy, no plan envelope)
```

### 7.3 Conversational follow-up flow (new, enabled by find-by-name)

```
User: "color the kick red"
AI:   find_channel_by_name("kick")
      → { matches: [{ index: 3, name: "Kick", score: 0.95 }] }
AI:   set_channel_color(3, 0xFF0000)
```

If multiple matches with similar score: AI asks the user before acting.

## 8. Error Handling

| Failure mode | Behavior |
|---|---|
| Bad index in plan item | Recorded in `errors[]`, item skipped, batch continues. |
| FL API throws on a setter call | Recorded in `errors[]`, item skipped, batch continues. |
| `general.saveUndo` not called before setters | Caught in bridge unit tests; failing test blocks merge. |
| Relay timeout (5s) on `apply_organization_plan` | Returned to AI as `RELAY_TIMEOUT`. AI tells user "the apply timed out — your project state is uncertain; try `undo` to revert anything that did apply, then try again." |
| `find_by_name` returns 0 matches | AI asks user to clarify. Never silently picks an unrelated index. |
| `find_by_name` returns multiple high-score matches (within 0.05 of top) | AI asks user to disambiguate. |
| Plan with all-empty optional fields | No-op, returns `applied = {0,0,0,0}` and `errors = []`. Treated as success. |

## 9. Testing

### 9.1 Bridge unit tests (`bridge/fl_studio/tests/`)

Tests run with mocked FL modules (`channels`, `mixer`, `patterns`, `playlist`, `general`) injected via `conftest.py`.

- `test_apply_plan_calls_save_undo_once` — exactly one `general.saveUndo` call per apply, before any setter.
- `test_apply_plan_partial_success` — mix valid + invalid indices; errors collected, valid items applied, `applied` counts correct.
- `test_apply_plan_empty_sections` — sections omitted or `[]` produce no calls and no errors.
- `test_apply_plan_no_op_item` — item with only `index` (no name/color/insert) is skipped, does not count as applied or error.
- `test_apply_plan_indexing_conventions` — playlist/pattern items use 1-indexed; channel/mixer items use 0-indexed; mismatches caught at Zod boundary, not bridge.
- `test_undo_calls_undo_up` — `_cmd_undo` invokes `general.undoUp()` exactly once.
- `test_save_project_calls_save_project_zero` — argument is exactly `0`.
- `test_find_by_name_ranking` — fixture set of 50 names, query "kick" returns Kick, Kick Layer, Kick Sub in score order.
- `test_find_by_name_cutoff` — query with no good matches returns `[]`, not low-score noise.
- `test_find_by_name_limit` — limit honored; default of 5 when omitted.

### 9.2 TypeScript tool registry tests (`apps/web/src/lib/ai/tools/__tests__/`)

- `composeTools.test.ts` — snapshot of the assembled `tools` object's keys + descriptions. Asserts no migrated tool changed name or description (regression guard for the refactor).
- `_shared.test.ts` — `relayTool` returns the right shape for success, relay error, and unknown error. Mocks `relay()`.

### 9.3 AI eval (lightweight, not blocking CI initially)

Six canned prompts dispatched against the live `streamText` with a mocked relay. Each asserts the **first tool the model picks**:

| Prompt | Expected first tool |
|---|---|
| "Organize this project" | `get_project_state` |
| "Rename channel 3 to KICK" | `rename_channel` |
| "Color the kick red" | `find_channel_by_name` |
| "Save the project" | `save_project` |
| "Undo" | `undo` |
| "What's in this project?" | `get_project_state` |

Run on PRs that touch `system-prompt.ts` or `tools/`. Failure surfaces a regression in tool selection caused by prompt drift. To avoid burning model budget on every CI run, eval is local-only initially; once we have recorded fixtures of expected tool-call streams, it can move to CI as a deterministic snapshot test.

### 9.4 Manual smoke test

Before merge:

1. Real FL Studio (macOS), real plugin, real WebSocket. Fresh project with 50 channels, 30 mixer tracks, 10 playlist tracks.
2. `"Organize this project"` → preview → confirm → verify visible renames + colors.
3. `Ctrl+Z` in FL → verify entire batch reverts as one undo step. **Critical check.**
4. If step 3 fails, switch to fallback: bridge returns op count, `undo` accepts `count`, AI loops.

## 10. Implementation Order

1. **Bridge handlers + tests.** Land `handlers_bulk.py` with full unit coverage. No changes to web app yet. Verifiable in isolation.
2. **Tool registry refactor (no behavior change).** Pull existing tools out of `route.ts` into `tools/{transport,channels,mixer,playlist,patterns,project}.ts`. Snapshot test asserts identical tool shape. Ship and verify nothing regresses.
3. **System prompt extraction.** Move the inline system string to `lib/ai/system-prompt.ts`.
4. **Add new tools to registry.** `apply_organization_plan`, `undo`, `save_project`, `find_*_by_name` land in their respective modules.
5. **Update system prompt.** Document the new tools to the model: when to use bulk apply vs per-item, when to call `save_project`, what `undo` covers, how to use `find_by_name` for follow-ups.
6. **Simplify the existing organize agent.** Delete `analysis-agent.ts` and the multi-stage internal `streamText` calls in `organization-agent.ts`. Replace with the new flow (Section 7.1). Ship behind a feature flag if risk feels high; otherwise direct.
7. **Manual smoke test on real FL Studio.** Verify undo grouping. If broken, add the count-based fallback.

Each step is independently shippable. Rollback to step N-1 is always possible.

## 11. Open Risks

- **FL undo grouping behavior** (Section 5.3). Mitigated by tests + manual verification + documented fallback.
- **LLM picking the wrong path.** Plan envelope is structured enough that the model could under-batch (one tool call per item) if the system prompt isn't explicit. Mitigated by the AI eval suite and prompt-engineered guidance: *"For organizing more than 3 items, always use `apply_organization_plan` in a single call."*
- **Plan size at 500 tracks.** Worst-case JSON is ~80–120 KB. Well within Vercel AI SDK tool-call limits. Spot-check before merge.
- **Backward compatibility of relay protocol.** New actions (`apply_organization_plan`, `undo`, `save_project`, `find_*_by_name`) require the bridge to be updated too. Older bridges return "unknown action" → AI surfaces gracefully. Document plugin update requirement in release notes.

## 12. Vault Documentation (post-implementation)

After this lands, file in `obsidian-studio-ai/wiki/`:

- **ADR**: `decisions/2026-04-15-ai-tool-registry.md` — captures the per-domain module pattern + the granular-vs-bulk-vs-mega-bulk decision (we picked granular + mega-bulk; rejected per-category bulk as redundant).
- **Component update**: `components/organization-agent.md` — replace the 3-stage internal sub-agent description with the new flow.
- **Concept**: `concepts/bulk-apply-pattern.md` — pattern of "single FL undo step wraps N setters via `general.saveUndo`" for future bridge work.
- **Index update**: register all three above in `index.md`.

Use the `vault-maintain` skill to file these.
