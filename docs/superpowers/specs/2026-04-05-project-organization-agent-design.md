# Project Organization Agent — Design Spec

## Overview

An AI agent that intelligently organizes FL Studio projects — both cleaning up messy existing projects and scaffolding new ones. The agent reads project state, analyzes MIDI data to infer instrument roles, classifies channels into role groups, and applies a coherent naming/color/routing scheme. Users preview and approve the plan before execution.

## Goals

- **Primary:** Smart naming and color-coding of channels, mixer tracks, playlist tracks, and patterns
- **Secondary:** Fix unrouted channels (assign to mixer inserts), light structural cleanup
- **Both new and existing projects** from day one

## Non-Goals (v1)

- Deep mixer restructuring (bus routing, effects chains)
- Loading instruments or plugins
- Writing MIDI patterns
- BPM/pitch adjustments
- VST parameter control or scanning

---

## Agent Architecture

Three-stage pipeline (two AI, one deterministic) using Vercel AI SDK's `ToolLoopAgent` and `generateText` with tool calling.

### Stage 1: Analysis Agent

**Purpose:** Read project state, inspect MIDI data, classify every channel by musical role.

**Model:** Claude Sonnet (reasoning-capable, moderate cost)

**Tools available:**
- `get_project_state` — returns full snapshot (channels, mixer, playlist, patterns)
- `get_pattern_notes` — returns MIDI note data for a channel/pattern (NEW command)

**Behavior:**
1. Calls `get_project_state` to get the full project snapshot
2. Reasons about each channel: plugin name, existing name, position
3. For ambiguous channels, calls `get_pattern_notes` to analyze note ranges, patterns, velocity
4. Produces a structured **Project Map** classifying every channel

**Output — Project Map:**
```json
{
  "channels": [
    {
      "index": 0,
      "currentName": "Channel 1",
      "plugin": "Sytrus",
      "inferredRole": "bass",
      "roleGroup": "bass",
      "confidence": "high",
      "reasoning": "Notes concentrated in C1-C2 range, mono pattern"
    },
    {
      "index": 1,
      "currentName": "Sampler",
      "plugin": "Sampler",
      "inferredRole": "kick",
      "roleGroup": "drums",
      "confidence": "high",
      "reasoning": "Single repeated note at low pitch, rhythmic on-beat pattern"
    }
  ],
}
```

**Implementation with Vercel AI SDK:**
```typescript
import { ToolLoopAgent, tool, Output, isStepCount } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';

const projectMapSchema = z.object({
  channels: z.array(z.object({
    index: z.number(),
    currentName: z.string(),
    plugin: z.string(),
    inferredRole: z.string(),
    roleGroup: z.enum(['drums', 'bass', 'leads', 'pads', 'fx', 'vocals', 'other']),
    confidence: z.enum(['high', 'medium', 'low']),
    reasoning: z.string(),
  })),
});

const analysisAgent = new ToolLoopAgent({
  model: anthropic('claude-sonnet-4-5-20250514'),
  instructions: ANALYSIS_SYSTEM_PROMPT,
  tools: {
    get_project_state: tool({
      description: 'Get the full FL Studio project state including all channels, mixer tracks, playlist tracks, and patterns',
      inputSchema: z.object({}),
      execute: async () => sendCommand('get_project_state'),
    }),
    get_pattern_notes: tool({
      description: 'Get MIDI notes from a specific channel in a pattern. Use this to analyze note ranges, rhythmic patterns, and velocity to infer instrument roles.',
      inputSchema: z.object({
        channel_index: z.number().describe('0-indexed channel in channel rack'),
        pattern_index: z.number().optional().describe('1-indexed pattern, defaults to current'),
      }),
      execute: async (params) => sendCommand('get_pattern_notes', params),
    }),
  },
  output: Output.object({ schema: projectMapSchema }),
  stopWhen: isStepCount(15), // budget: 1 get_project_state + up to 8 get_pattern_notes + structured output step + margin
});

const { output: projectMap } = await analysisAgent.generate({
  prompt: 'Analyze this FL Studio project. Read the project state, then inspect MIDI data for any channels where the role is ambiguous. Classify every channel by musical role.',
});
```

**Skipped for new projects** — user describes the genre/style instead.

### Stage 2: Organization Agent

**Purpose:** Take the Project Map (or genre description for new projects) and generate a complete organization plan.

**Model:** Claude Haiku (cheaper, mechanical task — applying rules to a known map)

**No tools needed** — pure reasoning over structured input, structured output.

The AI outputs **only naming and role assignments**. Color values are computed deterministically by code after the AI responds (see Color System section). This prevents the AI from picking arbitrary hex values.

**Output — Organization Plan (from AI):**
```json
{
  "channelAssignments": [
    { "index": 0, "newName": "808", "roleGroup": "bass" },
    { "index": 1, "newName": "Kick", "roleGroup": "drums" },
    { "index": 2, "newName": "Snare", "roleGroup": "drums" },
    { "index": 5, "newName": "Hi-Hat", "roleGroup": "drums" }
  ],
  "routingFixes": [
    { "channelIndex": 5, "assignedInsert": 6 }
  ]
}
```

A deterministic code layer then expands this into the full action list with color values, mixer track renames, playlist track updates, etc.

**Implementation:**
```typescript
// Schema for what the AI outputs (no colors, no action list)
const aiPlanSchema = z.object({
  channelAssignments: z.array(z.object({
    index: z.number(),
    newName: z.string(),
    roleGroup: z.enum(['drums', 'bass', 'leads', 'pads', 'fx', 'vocals', 'other']),
  })),
  routingFixes: z.array(z.object({
    channelIndex: z.number(),
    assignedInsert: z.number(),
  })),
});

const { output: aiPlan } = await generateText({
  model: anthropic('claude-haiku-4-5-20251001'),
  output: Output.object({ schema: aiPlanSchema }),
  system: ORGANIZATION_SYSTEM_PROMPT,
  prompt: `Project map: ${JSON.stringify(projectMap)}. Current state: ${JSON.stringify(projectState)}. Assign names and role groups. Fix unrouted channels.`,
});

// Deterministic expansion: code computes colors and builds typed action list
const fullPlan = expandPlan(aiPlan, projectState);
```

**Typed action schema (used internally after expansion):**
```typescript
const actionSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('rename_channel'), params: z.object({ index: z.number(), name: z.string() }) }),
  z.object({ type: z.literal('set_channel_color'), params: z.object({ index: z.number(), color: z.number() }) }),
  z.object({ type: z.literal('set_channel_insert'), params: z.object({ index: z.number(), insert: z.number() }) }),
  z.object({ type: z.literal('rename_mixer_track'), params: z.object({ index: z.number(), name: z.string() }) }),
  z.object({ type: z.literal('set_mixer_track_color'), params: z.object({ index: z.number(), color: z.number() }) }),
  z.object({ type: z.literal('rename_playlist_track'), params: z.object({ index: z.number(), name: z.string() }) }),
  z.object({ type: z.literal('set_playlist_track_color'), params: z.object({ index: z.number(), color: z.number() }) }),
  z.object({ type: z.literal('group_playlist_tracks'), params: z.object({ index: z.number(), count: z.number() }) }),
  z.object({ type: z.literal('rename_pattern'), params: z.object({ index: z.number(), name: z.string() }) }),
  z.object({ type: z.literal('set_pattern_color'), params: z.object({ index: z.number(), color: z.number() }) }),
]);
```

### Preview Adjustment Mechanism

When the user requests changes to the preview (e.g., "move channel 4 to pads"):

1. A new `generateText` call is made with:
   - The current AI plan (`channelAssignments` + `routingFixes`)
   - The user's feedback as a text amendment
   - Same `aiPlanSchema` output constraint
2. The AI returns an updated plan — full replacement, not a diff
3. The code layer re-expands into actions with updated colors
4. New preview is shown

```typescript
const { output: adjustedPlan } = await generateText({
  model: anthropic('claude-haiku-4-5-20251001'),
  output: Output.object({ schema: aiPlanSchema }),
  system: ORGANIZATION_SYSTEM_PROMPT,
  prompt: `Current plan: ${JSON.stringify(aiPlan)}. User feedback: "${userFeedback}". Update the plan accordingly. Return the full updated plan.`,
});

const updatedFullPlan = expandPlan(adjustedPlan, projectState);
```

This is cheap (~1K tokens per adjustment round) and stateless — no conversation history needed.

### Stage 3: Execution (No AI)

**Purpose:** Apply the approved plan as a batch of FL Studio commands.

**No model needed** — deterministic iteration over the plan's action list.

```typescript
async function executePlan(plan: OrganizationPlan): Promise<void> {
  for (const action of plan.actions) {
    await sendCommand(action.type, action.params);
    // Stream progress to chat UI
  }
}
```

---

## Color System

### Role Groups and Base Hues

| Role Group | Base Hue     | Hex Range        |
|-----------|-------------|------------------|
| Drums     | Red/Orange  | `#E53E3E` family |
| Bass      | Blue        | `#3182CE` family |
| Leads     | Green       | `#38A169` family |
| Pads      | Purple      | `#805AD5` family |
| FX        | Yellow/Gold | `#D69E2E` family |
| Vocals    | Pink        | `#D53F8C` family |
| Other     | Gray        | `#718096` family |

### Shade Variation Within Groups

- Each role group has a base RGB value defined in code
- Within a group, channels are ordered by their position in the channel rack
- First channel = darkest shade, last = lightest shade
- Shading is computed deterministically (e.g., lighten base by 10% per channel)
- Same color applied to: channel, associated mixer track, playlist track, and pattern

### Color Assignment is Deterministic

The AI assigns roles. The code maps roles to colors. The AI never picks hex values directly — this ensures consistency across projects and sessions.

---

## New FL Studio Command

### `get_pattern_notes`

**Purpose:** Read MIDI note data so the AI can infer instrument roles from note content.

**Parameters:**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `channel_index` | `int` | yes | 0-indexed channel in channel rack |
| `pattern_index` | `int` | no | 1-indexed pattern, defaults to current selected pattern |

**Response:**
```json
{
  "channel_index": 0,
  "pattern_index": 1,
  "notes": [
    { "pitch": 36, "velocity": 100, "position": 0.0, "length": 0.25 },
    { "pitch": 36, "velocity": 95, "position": 1.0, "length": 0.25 }
  ],
  "note_count": 2
}
```

**Implementation:** Uses FL Studio's MIDI scripting API to read note data from the specified channel and pattern. Notes are returned with pitch (0-127), velocity (1-127), position in beats, and length in beats (96 PPQ).

---

## Available fl-bridge Commands

All existing fl-bridge commands are carried forward unchanged. The Organization Agent uses a subset.

**Used by Organization Agent:**
- `get_project_state` — analysis entry point
- `rename_channel`, `set_channel_color`, `set_channel_insert` — channel operations
- `rename_mixer_track`, `set_mixer_track_color` — mixer operations
- `rename_playlist_track`, `set_playlist_track_color`, `group_playlist_tracks` — playlist operations
- `rename_pattern`, `set_pattern_color` — pattern operations

**Available but not used by Organization Agent (v1):**
- `set_bpm`, `set_pitch` — transport controls, not relevant to organization
- `set_channel_volume`, `set_channel_pan`, `set_channel_enabled` — channel audio, not visual organization
- `set_mixer_volume`, `set_mixer_pan`, `set_mixer_routing`, `set_mixer_eq` — deeper mixer work, deferred
- `add_midi_notes` — not organizing notes, just reading them

**Not available yet (needed for new project scaffolding):**
- `create_channel` — required to add channels for new project templates. Without this, new project scaffolding can only rename/recolor the default channels FL Studio creates on startup. This command needs to be implemented in the FL script.

---

## Error Handling

### Partial Execution Failure

If a command fails mid-execution (e.g., FL Studio rejects a rename):
- Log the failed action and continue with remaining actions
- After execution, report to the user: "Applied 28/30 changes. Failed: rename_channel(index: 5) — channel index out of range"
- No automatic rollback — partial organization is better than none, and all changes are individually reversible

### Stale State

The project may change between analysis and execution (user modifies something in FL Studio during the preview). Before execution:
- Re-fetch `get_project_state` and compare channel count against the plan
- If channel count changed, warn the user and suggest re-analyzing
- If channel count matches, proceed (minor changes like volume tweaks won't affect organization)

### Empty MIDI Data

If `get_pattern_notes` returns zero notes for a channel:
- The Analysis Agent falls back to plugin name and channel name for inference
- Marks confidence as "low" in the Project Map
- This is expected for empty channels or sample-based instruments with no MIDI

### FL Studio Bridge Disconnection

If the WebSocket connection to the plugin drops:
- Halt execution immediately
- Report which actions were completed and which remain
- User can retry after reconnecting

---

## User Flows

### Flow 1: Organize Existing Project

```
User: "Organize my project"
        |
  [Analysis Agent - Sonnet]
  -> calls get_project_state
  -> reasons about channels, identifies ambiguous ones
  -> calls get_pattern_notes for ambiguous channels (3-5 calls)
  -> produces Project Map with role classifications
        |
  [Organization Agent - Haiku]
  -> receives Project Map + project state
  -> generates plan: renames, colors by role group, routing fixes
        |
  [Preview in Chat UI]
  Shows grouped preview:
    Drums (red): Channel 1 -> "Kick", Channel 2 -> "Snare", Channel 5 -> "Hi-Hat"
    Bass (blue): Channel 3 -> "808"
    Leads (green): Channel 4 -> "Lead Synth"
    Routing fixes: Channel 6 unrouted -> assign to insert 6
    
  "Apply these changes?"
        |
  User tweaks: "Move channel 4 to pads, rest looks good"
        |
  [Organization Agent adjusts plan]
        |
  [Execution - batch commands]
  -> 30-40 commands fired sequentially
  -> progress streamed to chat
        |
  "Done! Project organized."
```

### Flow 2: New Project Scaffold

```
User: "I'm starting a trap beat"
        |
  [Organization Agent - Haiku]
  -> no analysis needed, skips Stage 1
  -> generates template based on genre description
        |
  [Preview in Chat UI]
  Shows template:
    Drums (red): Kick, 808, Snare, Hi-Hat, Open Hat, Perc
    Bass (blue): Sub Bass
    Leads (green): Lead 1, Lead 2
    Pads (purple): Pad, Atmosphere
    FX (gold): Riser, Impact
    
  "Set this up?"
        |
  User: "Add a vocal channel too"
        |
  [Adjusts plan]
        |
  [Execution]
  -> creates named, colored, routed empty project shell
        |
  "Done! Empty project shell ready."
```

### Preview Adjustment Flow

When the user requests changes to the preview:
1. A new `generateText` call is made with the current plan + user feedback (see Stage 2 adjustment mechanism)
2. The AI returns a full updated plan (not a diff)
3. Code re-expands with updated colors
4. New preview is shown
5. Repeat until user approves

---

## Token Cost Strategy

| Stage | Model | Estimated Tokens | Why This Model |
|-------|-------|-----------------|----------------|
| Analysis | Claude Sonnet | ~2-4K input, ~1-2K output | Needs reasoning to classify instruments from MIDI data |
| Organization | Claude Haiku | ~1-2K input, ~1K output | Mechanical — apply naming/color rules to known map |
| Preview adjustment | Claude Haiku | ~1K input, ~1K output | Small diff to existing plan |
| Execution | None | 0 | Deterministic command dispatch |

**Total per organization: ~5-8K tokens** (mostly Sonnet for analysis)

For new project scaffolding, only the Organization stage runs — even cheaper.

---

## Key Design Decisions

1. **Three-stage pipeline (two AI, one deterministic)** — separates understanding (expensive, reasoning-heavy) from planning (cheap, mechanical) from execution (no AI). The Project Map is a clean interface between stages 1 and 2.

2. **Deterministic colors** — the AI assigns roles, code assigns colors. Prevents random hex values and ensures visual consistency.

3. **Preview before execution** — user always approves. One round of feedback, not conversational back-and-forth.

4. **Best-guess inference** — the agent makes its best classification without asking the user mid-loop. User corrects in the preview if needed.

5. **New projects reuse the same pipeline** — just skip Stage 1. The Organization Agent handles both cleanup and scaffolding.

6. **`get_pattern_notes` is the only new command** — everything else reuses existing fl-bridge commands.
