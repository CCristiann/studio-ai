# Project Organization Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AI agent that intelligently organizes FL Studio projects — naming, coloring, and fixing routing — using a three-stage pipeline (Analysis, Organization, Execution).

**Architecture:** Three-stage pipeline. Stage 1 (Analysis Agent) uses Vercel AI SDK `ToolLoopAgent` with Claude Sonnet to read project state + MIDI data and classify channels by role. Stage 2 (Organization Agent) uses `generateText` with Claude Haiku to generate naming/role assignments. A deterministic code layer expands role assignments into colored action plans. Stage 3 executes the plan as batched relay commands.

**Tech Stack:** Vercel AI SDK v6, `@ai-sdk/anthropic`, Zod v4, Next.js 15 route handlers, Python FL Studio MIDI scripting API

**Spec:** `docs/superpowers/specs/2026-04-05-project-organization-agent-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `apps/web/src/lib/ai/organize/types.ts` | Zod schemas and TS types for Project Map, AI plan, typed actions, color system |
| `apps/web/src/lib/ai/organize/colors.ts` | Deterministic role→color mapping with shade variation |
| `apps/web/src/lib/ai/organize/analysis-agent.ts` | Stage 1: ToolLoopAgent that reads project state + MIDI, produces Project Map |
| `apps/web/src/lib/ai/organize/organization-agent.ts` | Stage 2: generateText that produces naming/role assignments |
| `apps/web/src/lib/ai/organize/expand-plan.ts` | Deterministic expansion: AI plan → typed action list with colors |
| `apps/web/src/lib/ai/organize/execute-plan.ts` | Stage 3: batch command execution with progress reporting |
| `apps/web/src/lib/ai/organize/prompts.ts` | System prompts for analysis and organization agents |
| `apps/web/src/app/api/ai/organize/route.ts` | HTTP endpoint for the organize flow |
| `bridge/fl_studio/handlers_organize.py` | New FL Studio handlers: get_project_state (enhanced), get_pattern_notes, rename_channel, set_channel_color, set_channel_insert, rename_playlist_track, set_playlist_track_color, group_playlist_tracks, rename_pattern, set_pattern_color |
| `packages/types/src/organize.ts` | Shared types for organization actions |

### Modified Files
| File | Change |
|------|--------|
| `bridge/fl_studio/device_studio_ai.py` | Import and register new handlers from handlers_organize.py |
| `apps/web/package.json` | Add `@ai-sdk/anthropic` dependency |

---

## Task 1: Install Anthropic AI SDK Provider

**Files:**
- Modify: `apps/web/package.json`

- [ ] **Step 1: Install the package**

Run:
```bash
cd apps/web && pnpm add @ai-sdk/anthropic
```

- [ ] **Step 2: Verify installation**

Run:
```bash
cd apps/web && pnpm list @ai-sdk/anthropic
```
Expected: Shows `@ai-sdk/anthropic` with a version number.

- [ ] **Step 3: Commit**

```bash
git add apps/web/package.json apps/web/pnpm-lock.yaml pnpm-lock.yaml
git commit -m "chore: add @ai-sdk/anthropic provider for organization agent"
```

---

## Task 2: Define Shared Organization Types

**Files:**
- Create: `packages/types/src/organize.ts`
- Modify: `packages/types/src/index.ts` (add re-export)

- [ ] **Step 1: Create the types file**

Create `packages/types/src/organize.ts`:

```typescript
/**
 * Types for the Project Organization Agent.
 * Used across the bridge (Python handlers) and web app (AI agent).
 */

// ── Role Groups ──

export type RoleGroup = "drums" | "bass" | "leads" | "pads" | "fx" | "vocals" | "other";

// ── Project Map (Stage 1 output) ──

export interface ChannelClassification {
  index: number;
  currentName: string;
  plugin: string;
  inferredRole: string;
  roleGroup: RoleGroup;
  confidence: "high" | "medium" | "low";
  reasoning: string;
}

export interface ProjectMap {
  channels: ChannelClassification[];
}

// ── AI Plan (Stage 2 output — no colors, no action list) ──

export interface ChannelAssignment {
  index: number;
  newName: string;
  roleGroup: RoleGroup;
}

export interface RoutingFix {
  channelIndex: number;
  assignedInsert: number;
}

export interface AIPlan {
  channelAssignments: ChannelAssignment[];
  routingFixes: RoutingFix[];
}

// ── Typed Actions (after deterministic expansion) ──

export type OrganizeAction =
  | { type: "rename_channel"; params: { index: number; name: string } }
  | { type: "set_channel_color"; params: { index: number; color: number } }
  | { type: "set_channel_insert"; params: { index: number; insert: number } }
  | { type: "rename_mixer_track"; params: { index: number; name: string } }
  | { type: "set_mixer_track_color"; params: { index: number; color: number } }
  | { type: "rename_playlist_track"; params: { index: number; name: string } }
  | { type: "set_playlist_track_color"; params: { index: number; color: number } }
  | { type: "group_playlist_tracks"; params: { index: number; count: number } }
  | { type: "rename_pattern"; params: { index: number; name: string } }
  | { type: "set_pattern_color"; params: { index: number; color: number } };

// ── Full Plan (preview + execution) ──

export interface PreviewGroup {
  roleGroup: RoleGroup;
  colorHex: string;
  channels: { index: number; oldName: string; newName: string }[];
}

export interface OrganizationPlan {
  actions: OrganizeAction[];
  preview: {
    groups: PreviewGroup[];
    routingFixes: { channelIndex: number; channelName: string; assignedInsert: number }[];
  };
}

// ── Enhanced Project State (returned by get_project_state) ──

export interface ChannelInfo {
  index: number;
  name: string;
  plugin: string;
  color: number;
  volume: number;
  pan: number;
  enabled: boolean;
  insert: number;
}

export interface MixerTrackInfo {
  index: number;
  name: string;
  color: number;
  volume: number;
  pan: number;
  muted: boolean;
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
}

export interface EnhancedProjectState {
  bpm: number;
  project_name: string;
  channels: ChannelInfo[];
  mixer_tracks: MixerTrackInfo[];
  playlist_tracks: PlaylistTrackInfo[];
  patterns: PatternInfo[];
}

// ── Pattern Notes (returned by get_pattern_notes) ──

export interface NoteInfo {
  pitch: number;
  velocity: number;
  position: number;
  length: number;
}

export interface PatternNotes {
  channel_index: number;
  pattern_index: number;
  notes: NoteInfo[];
  note_count: number;
}
```

- [ ] **Step 2: Re-export from index**

Add to `packages/types/src/index.ts`:

```typescript
export * from "./organize";
```

- [ ] **Step 3: Verify types compile**

Run:
```bash
cd apps/web && pnpm exec tsc --noEmit 2>&1 | head -20
```
Expected: No errors related to organize types.

- [ ] **Step 4: Commit**

```bash
git add packages/types/src/organize.ts packages/types/src/index.ts
git commit -m "feat: add shared types for project organization agent"
```

---

## Task 3: Implement Deterministic Color System

**Files:**
- Create: `apps/web/src/lib/ai/organize/colors.ts`

- [ ] **Step 1: Create the color module**

Create `apps/web/src/lib/ai/organize/colors.ts`:

```typescript
import type { RoleGroup } from "@repo/types";

/**
 * Deterministic role→color mapping.
 * AI assigns roles, this module assigns colors.
 * Colors are 24-bit RGB integers (same format FL Studio expects).
 */

interface RoleColor {
  base: [number, number, number]; // [R, G, B]
  hex: string; // for preview display
}

const ROLE_COLORS: Record<RoleGroup, RoleColor> = {
  drums:  { base: [229, 62, 62],   hex: "#E53E3E" },
  bass:   { base: [49, 130, 206],  hex: "#3182CE" },
  leads:  { base: [56, 161, 105],  hex: "#38A169" },
  pads:   { base: [128, 90, 213],  hex: "#805AD5" },
  fx:     { base: [214, 158, 46],  hex: "#D69E2E" },
  vocals: { base: [213, 63, 140],  hex: "#D53F8C" },
  other:  { base: [113, 128, 150], hex: "#718096" },
};

/**
 * Lighten an RGB color by a percentage (0-100).
 * Moves each channel toward 255.
 */
function lighten(rgb: [number, number, number], percent: number): [number, number, number] {
  const factor = percent / 100;
  return [
    Math.round(rgb[0] + (255 - rgb[0]) * factor),
    Math.round(rgb[1] + (255 - rgb[1]) * factor),
    Math.round(rgb[2] + (255 - rgb[2]) * factor),
  ];
}

/**
 * Convert RGB to 24-bit integer (FL Studio color format).
 */
function rgbToInt(rgb: [number, number, number]): number {
  return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2];
}

/**
 * Convert RGB to hex string for preview display.
 */
function rgbToHex(rgb: [number, number, number]): string {
  return "#" + rgb.map(c => c.toString(16).padStart(2, "0")).join("").toUpperCase();
}

/**
 * Get the color for a channel based on its role group and position within that group.
 *
 * @param roleGroup - The channel's role group
 * @param positionInGroup - 0-based index of this channel within its role group
 * @param groupSize - Total number of channels in this role group
 * @returns Object with `int` (FL Studio format) and `hex` (preview display)
 */
export function getChannelColor(
  roleGroup: RoleGroup,
  positionInGroup: number,
  groupSize: number,
): { int: number; hex: string } {
  const role = ROLE_COLORS[roleGroup];
  // First channel = base color, lighten by 10% per step, max 40% lighten
  const lightenPercent = groupSize <= 1
    ? 0
    : Math.min((positionInGroup / (groupSize - 1)) * 40, 40);
  const rgb = lighten(role.base, lightenPercent);
  return { int: rgbToInt(rgb), hex: rgbToHex(rgb) };
}

/**
 * Get the base hex color for a role group (used in preview headers).
 */
export function getRoleGroupHex(roleGroup: RoleGroup): string {
  return ROLE_COLORS[roleGroup].hex;
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/colors.ts
git commit -m "feat: add deterministic role-based color system for organization agent"
```

---

## Task 4: Implement Plan Expansion (AI Plan → Typed Actions)

**Files:**
- Create: `apps/web/src/lib/ai/organize/expand-plan.ts`

- [ ] **Step 1: Create the expand-plan module**

Create `apps/web/src/lib/ai/organize/expand-plan.ts`:

```typescript
import type {
  AIPlan,
  OrganizationPlan,
  OrganizeAction,
  PreviewGroup,
  EnhancedProjectState,
  RoleGroup,
} from "@repo/types";
import { getChannelColor, getRoleGroupHex } from "./colors";

/**
 * Expand an AI plan (names + role assignments) into a full organization plan
 * with deterministic colors and typed actions.
 */
export function expandPlan(
  aiPlan: AIPlan,
  projectState: EnhancedProjectState,
): OrganizationPlan {
  const actions: OrganizeAction[] = [];
  const groupMap = new Map<RoleGroup, { index: number; oldName: string; newName: string }[]>();

  // Group assignments by role for color calculation
  for (const assignment of aiPlan.channelAssignments) {
    const group = groupMap.get(assignment.roleGroup) ?? [];
    const channel = projectState.channels.find(c => c.index === assignment.index);
    group.push({
      index: assignment.index,
      oldName: channel?.name ?? `Channel ${assignment.index}`,
      newName: assignment.newName,
    });
    groupMap.set(assignment.roleGroup, group);
  }

  // Generate actions for each role group
  for (const [roleGroup, channels] of groupMap) {
    for (let i = 0; i < channels.length; i++) {
      const ch = channels[i];
      const color = getChannelColor(roleGroup, i, channels.length);

      // Rename and color the channel
      actions.push({ type: "rename_channel", params: { index: ch.index, name: ch.newName } });
      actions.push({ type: "set_channel_color", params: { index: ch.index, color: color.int } });

      // Find the channel's mixer insert and update it too
      const channel = projectState.channels.find(c => c.index === ch.index);
      if (channel && channel.insert >= 0) {
        actions.push({ type: "rename_mixer_track", params: { index: channel.insert, name: ch.newName } });
        actions.push({ type: "set_mixer_track_color", params: { index: channel.insert, color: color.int } });
      }

      // Pattern: use 1-indexed (channel index + 1) as a heuristic
      const patternIndex = ch.index + 1;
      const pattern = projectState.patterns.find(p => p.index === patternIndex);
      if (pattern) {
        actions.push({ type: "rename_pattern", params: { index: patternIndex, name: ch.newName } });
        actions.push({ type: "set_pattern_color", params: { index: patternIndex, color: color.int } });
      }
    }
  }

  // Routing fixes
  for (const fix of aiPlan.routingFixes) {
    actions.push({ type: "set_channel_insert", params: { index: fix.channelIndex, insert: fix.assignedInsert } });
    // Also name/color the newly assigned mixer track
    const assignment = aiPlan.channelAssignments.find(a => a.index === fix.channelIndex);
    if (assignment) {
      const group = groupMap.get(assignment.roleGroup) ?? [];
      const posInGroup = group.findIndex(c => c.index === fix.channelIndex);
      const color = getChannelColor(assignment.roleGroup, Math.max(posInGroup, 0), group.length);
      actions.push({ type: "rename_mixer_track", params: { index: fix.assignedInsert, name: assignment.newName } });
      actions.push({ type: "set_mixer_track_color", params: { index: fix.assignedInsert, color: color.int } });
    }
  }

  // Build preview
  const groups: PreviewGroup[] = [];
  for (const [roleGroup, channels] of groupMap) {
    groups.push({
      roleGroup,
      colorHex: getRoleGroupHex(roleGroup),
      channels,
    });
  }

  const routingFixPreviews = aiPlan.routingFixes.map(fix => {
    const assignment = aiPlan.channelAssignments.find(a => a.index === fix.channelIndex);
    return {
      channelIndex: fix.channelIndex,
      channelName: assignment?.newName ?? `Channel ${fix.channelIndex}`,
      assignedInsert: fix.assignedInsert,
    };
  });

  return {
    actions,
    preview: { groups, routingFixes: routingFixPreviews },
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/expand-plan.ts
git commit -m "feat: add deterministic plan expansion (AI plan → typed actions with colors)"
```

---

## Task 5: Write Zod Schemas for AI Agent I/O

**Files:**
- Create: `apps/web/src/lib/ai/organize/types.ts`

- [ ] **Step 1: Create the Zod schemas file**

Create `apps/web/src/lib/ai/organize/types.ts`:

```typescript
import { z } from "zod";

/**
 * Zod schemas for AI agent input/output validation.
 * These are used with Vercel AI SDK's Output.object() for structured generation.
 */

// ── Stage 1: Analysis Agent output ──

export const roleGroupSchema = z.enum([
  "drums", "bass", "leads", "pads", "fx", "vocals", "other",
]);

export const projectMapSchema = z.object({
  channels: z.array(z.object({
    index: z.number(),
    currentName: z.string(),
    plugin: z.string(),
    inferredRole: z.string().describe("Specific role like 'kick', 'snare', 'sub-bass', 'lead synth'"),
    roleGroup: roleGroupSchema,
    confidence: z.enum(["high", "medium", "low"]),
    reasoning: z.string().describe("Brief explanation of why this classification was chosen"),
  })),
});

// ── Stage 2: Organization Agent output ──

export const aiPlanSchema = z.object({
  channelAssignments: z.array(z.object({
    index: z.number().describe("0-indexed channel index"),
    newName: z.string().max(128).describe("New display name for the channel"),
    roleGroup: roleGroupSchema,
  })),
  routingFixes: z.array(z.object({
    channelIndex: z.number().describe("0-indexed channel that needs routing"),
    assignedInsert: z.number().describe("Mixer insert index to route to"),
  })),
});

// Type aliases extracted from schemas
export type ProjectMapOutput = z.infer<typeof projectMapSchema>;
export type AIPlanOutput = z.infer<typeof aiPlanSchema>;
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/types.ts
git commit -m "feat: add Zod schemas for organization agent AI I/O"
```

---

## Task 6: Write Agent System Prompts

**Files:**
- Create: `apps/web/src/lib/ai/organize/prompts.ts`

- [ ] **Step 1: Create the prompts file**

Create `apps/web/src/lib/ai/organize/prompts.ts`:

```typescript
/**
 * System prompts for the organization agent stages.
 */

export const ANALYSIS_SYSTEM_PROMPT = `You are a music production expert analyzing an FL Studio project. Your job is to classify every channel by its musical role.

## How to classify channels

1. First call get_project_state to see all channels, mixer tracks, playlist tracks, and patterns.
2. Look at each channel's plugin name and existing name for obvious roles:
   - "Kick", "Snare", "HH", "Hat" → drums
   - "808", "Sub", "Bass" → bass
   - "Lead", "Pluck", "Arp" → leads
   - "Pad", "Atmosphere", "Ambient" → pads
   - "FX", "Riser", "Impact", "Sweep" → fx
   - "Vocal", "Vox", "Adlib" → vocals
3. For channels where the name and plugin are ambiguous (e.g., "Channel 1", "Sampler", "Sytrus"), call get_pattern_notes to inspect the MIDI data:
   - Notes concentrated below C2 (pitch < 48) → likely bass or kick
   - Single repeated notes with short lengths on beat positions → likely drums
   - Notes spanning a wide pitch range with varying velocities → likely lead or pad
   - Very long sustained notes → likely pad
   - Short staccato notes in higher registers → likely lead or arp
   - No notes at all → classify based on plugin name only, mark confidence "low"
4. If still unsure, use your best judgment and mark confidence as "medium".

## Role groups
- drums: kick, snare, hi-hat, cymbal, percussion, drum machine
- bass: sub-bass, 808, bass synth, bass guitar
- leads: lead synth, pluck, arp, bell, keys, piano
- pads: pad, atmosphere, ambient, texture, drone
- fx: riser, impact, sweep, noise, transition
- vocals: main vocal, backing vocal, ad-lib, vocal chop
- other: anything that doesn't fit above

Be efficient with get_pattern_notes calls — only use it for channels you can't classify from name/plugin alone.`;

export const ORGANIZATION_SYSTEM_PROMPT = `You are a music production assistant that organizes FL Studio projects. Given a Project Map (channel classifications), assign clean, descriptive names to each channel.

## Naming rules
- Use short, clear names that a producer would recognize at a glance
- Max 20 characters per name
- Use standard music production terminology
- If the project already has good names, keep them
- For drums: "Kick", "Snare", "Hi-Hat", "Open Hat", "Perc", "Clap", "Rim"
- For bass: "808", "Sub Bass", "Bass", "Mid Bass"
- For leads: "Lead", "Lead 2", "Pluck", "Arp", "Bell", "Keys"
- For pads: "Pad", "Atmosphere", "Texture", "Strings"
- For FX: "Riser", "Impact", "Sweep", "FX"
- For vocals: "Vocal", "Ad-lib", "Vocal Chop", "Backing Vox"
- Number duplicates: "Lead 1", "Lead 2" (not "Lead", "Lead")

## Routing fixes
- Check if any channels have insert value of -1 or 0 (Master). If so, assign them to the next available mixer insert.
- Don't reassign channels that already have a dedicated insert.

## Output
Return channelAssignments with a name and roleGroup for EVERY channel in the project map. Return routingFixes only for channels that need them.`;

export const SCAFFOLD_SYSTEM_PROMPT = `You are a music production assistant that creates FL Studio project templates. Given a genre or style description, generate a list of channels with appropriate names and role groups.

## Rules
- Create a realistic set of channels for the genre (8-16 channels typical)
- Include a balanced mix: drums, bass, melodic, and atmospheric elements
- Use standard names a producer would expect
- Assign each channel to a role group

## Common genre templates
- Trap: Kick, 808, Snare, Clap, Hi-Hat, Open Hat, Perc, Lead, Lead 2, Pad, FX, Vocal
- Lo-fi: Kick, Snare, Hi-Hat, Bass, Keys, Guitar, Pad, Vinyl FX, Vocal Chop
- House: Kick, Clap, Hi-Hat, Shaker, Bass, Lead, Pad, Stab, FX, Vocal
- Pop: Kick, Snare, Hi-Hat, Bass, Piano, Guitar, Synth Lead, Pad, Strings, Vocal
- Drill: Kick, 808, Snare, Hi-Hat, Perc, Lead, Pad, FX, Vocal
- R&B: Kick, Snare, Hi-Hat, Bass, Keys, Guitar, Pad, Strings, Vocal, Ad-lib

Adapt based on the user's specific description. If they mention specific instruments, include them.`;
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/prompts.ts
git commit -m "feat: add system prompts for analysis, organization, and scaffold agents"
```

---

## Task 7: Implement Analysis Agent (Stage 1)

**Files:**
- Create: `apps/web/src/lib/ai/organize/analysis-agent.ts`

- [ ] **Step 1: Create the analysis agent module**

Create `apps/web/src/lib/ai/organize/analysis-agent.ts`:

```typescript
import { ToolLoopAgent, tool, Output, isStepCount } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { z } from "zod";
import { relay } from "@/lib/relay";
import { projectMapSchema } from "./types";
import { ANALYSIS_SYSTEM_PROMPT } from "./prompts";
import type { ProjectMap, EnhancedProjectState } from "@repo/types";

/**
 * Stage 1: Analysis Agent
 *
 * Reads FL Studio project state and MIDI data to classify every channel
 * by musical role. Uses Claude Sonnet with tool calling in an agentic loop.
 *
 * @returns ProjectMap with channel classifications, plus the raw project state
 */
export async function runAnalysis(userId: string): Promise<{
  projectMap: ProjectMap;
  projectState: EnhancedProjectState;
}> {
  let capturedState: EnhancedProjectState | null = null;

  const agent = new ToolLoopAgent({
    model: anthropic("claude-sonnet-4-5-20250514"),
    instructions: ANALYSIS_SYSTEM_PROMPT,
    tools: {
      get_project_state: tool({
        description: "Get the full FL Studio project state including all channels, mixer tracks, playlist tracks, and patterns with their names, colors, and routing.",
        inputSchema: z.object({}),
        execute: async () => {
          const result = await relay(userId, "get_project_state", {});
          if (result.success) {
            capturedState = result.data as EnhancedProjectState;
          }
          return result.success
            ? { success: true, data: result.data }
            : { success: false, error: result.error };
        },
      }),
      get_pattern_notes: tool({
        description: "Get MIDI notes from a specific channel in a pattern. Use this to analyze note ranges, rhythmic patterns, and velocity to infer instrument roles when the channel name and plugin are ambiguous.",
        inputSchema: z.object({
          channel_index: z.number().describe("0-indexed channel in channel rack"),
          pattern_index: z.number().optional().describe("1-indexed pattern, defaults to 1"),
        }),
        execute: async (params) => {
          const result = await relay(userId, "get_pattern_notes", {
            channel_index: params.channel_index,
            pattern_index: params.pattern_index ?? 1,
          });
          return result.success
            ? { success: true, data: result.data }
            : { success: false, error: result.error };
        },
      }),
    },
    output: Output.object({ schema: projectMapSchema }),
    stopWhen: isStepCount(15),
  });

  const { output } = await agent.generate({
    prompt: "Analyze this FL Studio project. Read the project state, then inspect MIDI data for any channels where the role is ambiguous from the name and plugin alone. Classify every channel by musical role.",
  });

  if (!output) {
    throw new Error("Analysis agent did not produce a project map");
  }

  if (!capturedState) {
    throw new Error("Analysis agent did not call get_project_state");
  }

  return { projectMap: output as ProjectMap, projectState: capturedState };
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/analysis-agent.ts
git commit -m "feat: implement analysis agent (Stage 1) with ToolLoopAgent"
```

---

## Task 8: Implement Organization Agent (Stage 2)

**Files:**
- Create: `apps/web/src/lib/ai/organize/organization-agent.ts`

- [ ] **Step 1: Create the organization agent module**

Create `apps/web/src/lib/ai/organize/organization-agent.ts`:

```typescript
import { generateText, Output } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { aiPlanSchema } from "./types";
import { ORGANIZATION_SYSTEM_PROMPT, SCAFFOLD_SYSTEM_PROMPT } from "./prompts";
import type { AIPlan, ProjectMap, EnhancedProjectState } from "@repo/types";

/**
 * Stage 2: Organization Agent (for existing projects)
 *
 * Takes a Project Map and generates naming/role assignments.
 * No tool calling — pure structured output from Claude Haiku.
 */
export async function runOrganization(
  projectMap: ProjectMap,
  projectState: EnhancedProjectState,
): Promise<AIPlan> {
  const { output } = await generateText({
    model: anthropic("claude-haiku-4-5-20251001"),
    output: Output.object({ schema: aiPlanSchema }),
    system: ORGANIZATION_SYSTEM_PROMPT,
    prompt: `Project map:\n${JSON.stringify(projectMap, null, 2)}\n\nCurrent project state (${projectState.channels.length} channels, ${projectState.mixer_tracks.length} mixer tracks):\n${JSON.stringify({ channels: projectState.channels, mixer_tracks: projectState.mixer_tracks }, null, 2)}\n\nAssign names and role groups for every channel. Fix any unrouted channels.`,
  });

  if (!output) {
    throw new Error("Organization agent did not produce a plan");
  }

  return output as AIPlan;
}

/**
 * Stage 2: Organization Agent (for new project scaffolding)
 *
 * Generates a template plan based on genre description.
 * No analysis stage needed.
 */
export async function runScaffold(genreDescription: string): Promise<AIPlan> {
  const { output } = await generateText({
    model: anthropic("claude-haiku-4-5-20251001"),
    output: Output.object({ schema: aiPlanSchema }),
    system: SCAFFOLD_SYSTEM_PROMPT,
    prompt: `Create a project template for: ${genreDescription}\n\nGenerate channelAssignments starting from index 0. Leave routingFixes empty (new projects have no existing routing to fix — channels will be auto-routed by index).`,
  });

  if (!output) {
    throw new Error("Scaffold agent did not produce a plan");
  }

  return output as AIPlan;
}

/**
 * Adjust an existing plan based on user feedback.
 * Returns a full replacement plan (not a diff).
 */
export async function adjustPlan(
  currentPlan: AIPlan,
  userFeedback: string,
): Promise<AIPlan> {
  const { output } = await generateText({
    model: anthropic("claude-haiku-4-5-20251001"),
    output: Output.object({ schema: aiPlanSchema }),
    system: ORGANIZATION_SYSTEM_PROMPT,
    prompt: `Current plan:\n${JSON.stringify(currentPlan, null, 2)}\n\nUser feedback: "${userFeedback}"\n\nUpdate the plan based on the feedback. Return the complete updated plan (all channels, not just changed ones).`,
  });

  if (!output) {
    throw new Error("Plan adjustment did not produce output");
  }

  return output as AIPlan;
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/organization-agent.ts
git commit -m "feat: implement organization agent (Stage 2) with structured output"
```

---

## Task 9: Implement Plan Execution (Stage 3)

**Files:**
- Create: `apps/web/src/lib/ai/organize/execute-plan.ts`

- [ ] **Step 1: Create the execution module**

Create `apps/web/src/lib/ai/organize/execute-plan.ts`:

```typescript
import { relay, RelayError } from "@/lib/relay";
import type { OrganizationPlan, OrganizeAction, EnhancedProjectState } from "@repo/types";

export interface ExecutionResult {
  totalActions: number;
  completedActions: number;
  failures: { action: OrganizeAction; error: string }[];
}

/**
 * Stage 3: Execute an approved organization plan.
 *
 * Fires commands sequentially via the relay.
 * Continues on failure (partial organization is better than none).
 * Calls onProgress for each completed action.
 */
export async function executePlan(
  userId: string,
  plan: OrganizationPlan,
  onProgress?: (completed: number, total: number) => void,
): Promise<ExecutionResult> {
  const result: ExecutionResult = {
    totalActions: plan.actions.length,
    completedActions: 0,
    failures: [],
  };

  for (const action of plan.actions) {
    try {
      const response = await relay(userId, action.type, action.params);
      if (!response.success) {
        result.failures.push({ action, error: response.error ?? "Unknown error" });
      }
    } catch (e) {
      const message = e instanceof RelayError ? e.message : "Relay failed";
      result.failures.push({ action, error: message });
    }

    result.completedActions++;
    onProgress?.(result.completedActions, result.totalActions);
  }

  return result;
}

/**
 * Validate that the project state hasn't changed significantly since analysis.
 * Returns true if safe to proceed, false if re-analysis is recommended.
 */
export async function validateStateBeforeExecution(
  userId: string,
  expectedChannelCount: number,
): Promise<{ valid: boolean; currentChannelCount: number }> {
  try {
    const response = await relay(userId, "get_project_state", {});
    if (!response.success) {
      return { valid: false, currentChannelCount: -1 };
    }
    const state = response.data as EnhancedProjectState;
    return {
      valid: state.channels.length === expectedChannelCount,
      currentChannelCount: state.channels.length,
    };
  } catch {
    return { valid: false, currentChannelCount: -1 };
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/ai/organize/execute-plan.ts
git commit -m "feat: implement plan execution (Stage 3) with progress tracking and error handling"
```

---

## Task 10: Implement the Organize API Route

**Files:**
- Create: `apps/web/src/app/api/ai/organize/route.ts`

- [ ] **Step 1: Create the route handler**

Create `apps/web/src/app/api/ai/organize/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { rateLimit } from "@/lib/rate-limit";
import { runAnalysis } from "@/lib/ai/organize/analysis-agent";
import { runOrganization, runScaffold, adjustPlan } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { executePlan, validateStateBeforeExecution } from "@/lib/ai/organize/execute-plan";
import type { AIPlan, EnhancedProjectState } from "@repo/types";

async function getUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  const session = await auth();
  return session?.userId ?? null;
}

/**
 * POST /api/ai/organize
 *
 * Body variants:
 *   { action: "analyze" }                           → Run analysis + organization, return preview
 *   { action: "scaffold", genre: string }           → Generate new project template, return preview
 *   { action: "adjust", plan: AIPlan, feedback: string } → Adjust plan based on feedback
 *   { action: "execute", plan: AIPlan, channelCount: number } → Execute approved plan
 */
export async function POST(req: Request) {
  const userId = await getUserId(req);
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { success } = rateLimit(`organize:${userId}`, { limit: 10, windowMs: 60_000 });
  if (!success) {
    return NextResponse.json({ error: "Rate limit exceeded" }, { status: 429 });
  }

  const body = await req.json();
  const { action } = body;

  try {
    if (action === "analyze") {
      // Stage 1 + 2: Analyze project → Generate plan → Return preview
      const { projectMap, projectState } = await runAnalysis(userId);
      const aiPlan = await runOrganization(projectMap, projectState);
      const fullPlan = expandPlan(aiPlan, projectState);

      return NextResponse.json({
        success: true,
        aiPlan,
        plan: fullPlan,
        projectState,
      });
    }

    if (action === "scaffold") {
      const { genre } = body as { genre: string };
      if (!genre) {
        return NextResponse.json({ error: "genre is required" }, { status: 400 });
      }
      const aiPlan = await runScaffold(genre);
      // For scaffolding, we create a synthetic project state (empty project)
      const emptyState: EnhancedProjectState = {
        bpm: 140,
        project_name: "New Project",
        channels: aiPlan.channelAssignments.map((a, i) => ({
          index: i, name: `Channel ${i + 1}`, plugin: "Sampler",
          color: 0, volume: 0.8, pan: 0, enabled: true, insert: i + 1,
        })),
        mixer_tracks: aiPlan.channelAssignments.map((a, i) => ({
          index: i + 1, name: `Insert ${i + 1}`, color: 0,
          volume: 0.8, pan: 0, muted: false,
        })),
        playlist_tracks: [],
        patterns: aiPlan.channelAssignments.map((a, i) => ({
          index: i + 1, name: `Pattern ${i + 1}`, color: 0,
        })),
      };
      const fullPlan = expandPlan(aiPlan, emptyState);

      return NextResponse.json({
        success: true,
        aiPlan,
        plan: fullPlan,
        projectState: emptyState,
      });
    }

    if (action === "adjust") {
      const { plan: currentPlan, feedback, projectState } = body as {
        plan: AIPlan;
        feedback: string;
        projectState: EnhancedProjectState;
      };
      if (!currentPlan || !feedback) {
        return NextResponse.json({ error: "plan and feedback are required" }, { status: 400 });
      }
      const adjustedAiPlan = await adjustPlan(currentPlan, feedback);
      const fullPlan = expandPlan(adjustedAiPlan, projectState);

      return NextResponse.json({
        success: true,
        aiPlan: adjustedAiPlan,
        plan: fullPlan,
      });
    }

    if (action === "execute") {
      const { plan: aiPlan, channelCount, projectState } = body as {
        plan: AIPlan;
        channelCount: number;
        projectState: EnhancedProjectState;
      };
      if (!aiPlan) {
        return NextResponse.json({ error: "plan is required" }, { status: 400 });
      }

      // Validate state hasn't changed
      const validation = await validateStateBeforeExecution(userId, channelCount);
      if (!validation.valid) {
        return NextResponse.json({
          success: false,
          error: "stale_state",
          message: `Project changed since analysis. Expected ${channelCount} channels, found ${validation.currentChannelCount}. Please re-analyze.`,
        }, { status: 409 });
      }

      const fullPlan = expandPlan(aiPlan, projectState);
      const result = await executePlan(userId, fullPlan);

      return NextResponse.json({
        success: result.failures.length === 0,
        result,
      });
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/app/api/ai/organize/route.ts
git commit -m "feat: add /api/ai/organize route handler for the organization agent pipeline"
```

---

## Task 11: Add FL Studio Handlers — Enhanced get_project_state

**Files:**
- Create: `bridge/fl_studio/handlers_organize.py`
- Modify: `bridge/fl_studio/device_studio_ai.py`

- [ ] **Step 1: Create the new handlers file**

Create `bridge/fl_studio/handlers_organize.py`:

```python
"""FL Studio handlers for the Project Organization Agent.

These handlers provide the enhanced project state and channel/mixer/playlist/pattern
manipulation commands needed by the organization agent.
"""


def _cmd_get_project_state(params):
    """Get enhanced project state with channels, mixer, playlist, and patterns."""
    import channels
    import mixer
    import patterns
    import playlist
    import general

    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"

    # Channel Rack (0-indexed)
    channel_list = []
    for i in range(channels.channelCount()):
        channel_list.append({
            "index": i,
            "name": channels.getChannelName(i),
            "plugin": channels.getChannelName(i, True),  # True = plugin name
            "color": channels.getChannelColor(i) & 0xFFFFFF,
            "volume": round(channels.getChannelVolume(i), 3),
            "pan": round(channels.getChannelPan(i), 3),
            "enabled": not channels.isChannelMuted(i),
            "insert": channels.getTargetFxTrack(i),
        })

    # Mixer tracks (0-indexed, skip unnamed "Insert N" tracks for brevity)
    mixer_list = []
    for i in range(mixer.trackCount()):
        name = mixer.getTrackName(i)
        mixer_list.append({
            "index": i,
            "name": name,
            "color": mixer.getTrackColor(i) & 0xFFFFFF,
            "volume": round(mixer.getTrackVolume(i), 3),
            "pan": round(mixer.getTrackPan(i), 3),
            "muted": bool(mixer.isTrackMuted(i)),
        })

    # Playlist tracks (1-indexed)
    playlist_list = []
    for i in range(1, playlist.trackCount() + 1):
        name = playlist.getTrackName(i)
        if name:
            playlist_list.append({
                "index": i,
                "name": name,
                "color": playlist.getTrackColor(i) & 0xFFFFFF,
            })

    # Patterns (1-indexed)
    pattern_list = []
    for i in range(1, patterns.patternCount() + 1):
        pattern_list.append({
            "index": i,
            "name": patterns.getPatternName(i),
            "color": patterns.getPatternColor(i) & 0xFFFFFF,
        })

    return {
        "bpm": bpm,
        "project_name": project_name,
        "channels": channel_list,
        "mixer_tracks": mixer_list,
        "playlist_tracks": playlist_list,
        "patterns": pattern_list,
    }


def _cmd_get_pattern_notes(params):
    """Get MIDI notes from a channel in a pattern."""
    import channels
    import patterns
    import general

    channel_index = int(params.get("channel_index", 0))
    pattern_index = int(params.get("pattern_index", 1))

    if channel_index < 0 or channel_index >= channels.channelCount():
        raise ValueError("channel_index %d out of range" % channel_index)
    if pattern_index < 1 or pattern_index > patterns.patternCount():
        raise ValueError("pattern_index %d out of range" % pattern_index)

    # Select the pattern so we can read its notes
    patterns.jumpToPattern(pattern_index)

    # Read grid bits and note properties
    # FL Studio's API uses getGridBit for on/off and getGridBitWithFlags for details
    ppq = general.getRecPPQ()  # Ticks per quarter note (typically 96)
    notes = []

    # Scan grid: FL Studio stores notes per step in the step sequencer
    # For piano roll data, we use channels.getGridBit at each step
    # Note: This is a simplified approach — full piano roll note extraction
    # requires iterating through the score log
    pattern_length = patterns.getPatternLength(pattern_index)
    if pattern_length <= 0:
        return {
            "channel_index": channel_index,
            "pattern_index": pattern_index,
            "notes": [],
            "note_count": 0,
        }

    # Use score log to get actual piano roll notes
    # channels.getGridBit only works for step sequencer
    # For piano roll, we need to use the MIDI score event approach
    score_log_count = channels.getActivityLevel(channel_index)

    # Simplified: read step sequencer grid as fallback
    steps = channels.getRecEventId(channel_index)
    grid_notes = []
    for step in range(pattern_length):
        if channels.getGridBit(channel_index, step):
            position = step / ppq  # Convert ticks to beats
            grid_notes.append({
                "pitch": 60,  # Step sequencer doesn't store pitch per step
                "velocity": 100,
                "position": round(position, 4),
                "length": round(1.0 / ppq, 4),
            })

    return {
        "channel_index": channel_index,
        "pattern_index": pattern_index,
        "notes": grid_notes,
        "note_count": len(grid_notes),
    }


# ── Channel operations ──

def _cmd_rename_channel(params):
    """Rename a channel in the Channel Rack."""
    import channels
    index = int(params.get("index", 0))
    name = str(params.get("name", ""))[:128]
    channels.setChannelName(index, name)
    return {"index": index, "name": name}


def _cmd_set_channel_color(params):
    """Set a channel's color (24-bit RGB integer)."""
    import channels
    index = int(params.get("index", 0))
    color = int(params.get("color", 0)) & 0xFFFFFF
    channels.setChannelColor(index, color)
    return {"index": index, "color": color}


def _cmd_set_channel_insert(params):
    """Route a channel to a mixer insert."""
    import channels
    index = int(params.get("index", 0))
    insert = int(params.get("insert", 0))
    channels.setTargetFxTrack(index, insert)
    return {"index": index, "insert": insert}


# ── Mixer operations ──

def _cmd_rename_mixer_track(params):
    """Rename a mixer track."""
    import mixer
    index = int(params.get("index", 0))
    name = str(params.get("name", ""))[:128]
    mixer.setTrackName(index, name)
    return {"index": index, "name": name}


def _cmd_set_mixer_track_color(params):
    """Set a mixer track's color (24-bit RGB integer)."""
    import mixer
    index = int(params.get("index", 0))
    color = int(params.get("color", 0)) & 0xFFFFFF
    mixer.setTrackColor(index, color)
    return {"index": index, "color": color}


# ── Playlist operations ──

def _cmd_rename_playlist_track(params):
    """Rename a playlist track (1-indexed)."""
    import playlist
    index = int(params.get("index", 1))
    name = str(params.get("name", ""))[:128]
    playlist.setTrackName(index, name)
    return {"index": index, "name": name}


def _cmd_set_playlist_track_color(params):
    """Set a playlist track's color (1-indexed, 24-bit RGB)."""
    import playlist
    index = int(params.get("index", 1))
    color = int(params.get("color", 0)) & 0xFFFFFF
    playlist.setTrackColor(index, color)
    return {"index": index, "color": color}


def _cmd_group_playlist_tracks(params):
    """Group playlist tracks under a parent (1-indexed)."""
    import playlist
    index = int(params.get("index", 1))
    count = int(params.get("count", 1))
    # FL Studio groups by setting consecutive tracks as children of the parent
    # The parent track is 'index', and the next 'count' tracks become children
    for i in range(index + 1, index + 1 + count):
        if i <= playlist.trackCount():
            playlist.setTrackActivityLevel(i, 1)  # Indent under parent
    return {"index": index, "count": count}


# ── Pattern operations ──

def _cmd_rename_pattern(params):
    """Rename a pattern (1-indexed)."""
    import patterns
    index = int(params.get("index", 1))
    name = str(params.get("name", ""))[:128]
    patterns.setPatternName(index, name)
    return {"index": index, "name": name}


def _cmd_set_pattern_color(params):
    """Set a pattern's color (1-indexed, 24-bit RGB)."""
    import patterns
    index = int(params.get("index", 1))
    color = int(params.get("color", 0)) & 0xFFFFFF
    patterns.setPatternColor(index, color)
    return {"index": index, "color": color}


# ── Registration ──

ORGANIZE_HANDLERS = {
    "get_project_state": _cmd_get_project_state,
    "get_pattern_notes": _cmd_get_pattern_notes,
    "rename_channel": _cmd_rename_channel,
    "set_channel_color": _cmd_set_channel_color,
    "set_channel_insert": _cmd_set_channel_insert,
    "rename_mixer_track": _cmd_rename_mixer_track,
    "set_mixer_track_color": _cmd_set_mixer_track_color,
    "rename_playlist_track": _cmd_rename_playlist_track,
    "set_playlist_track_color": _cmd_set_playlist_track_color,
    "group_playlist_tracks": _cmd_group_playlist_tracks,
    "rename_pattern": _cmd_rename_pattern,
    "set_pattern_color": _cmd_set_pattern_color,
}
```

- [ ] **Step 2: Register handlers in device_studio_ai.py**

In `bridge/fl_studio/device_studio_ai.py`, add the import and merge handlers. Add this import near the top (after the existing imports):

```python
from bridge.fl_studio.handlers_organize import ORGANIZE_HANDLERS
```

Then replace the `_HANDLERS` dictionary at line 266 with:

```python
_HANDLERS = {
    "set_bpm": _cmd_set_bpm,
    "get_state": _cmd_get_state,
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
}
```

Note: `get_project_state` from ORGANIZE_HANDLERS overrides the alias `get_project_state: _cmd_get_state` that was there before, providing the enhanced version with channels, mixer, playlist, and patterns.

- [ ] **Step 3: Commit**

```bash
git add bridge/fl_studio/handlers_organize.py bridge/fl_studio/device_studio_ai.py
git commit -m "feat: add FL Studio handlers for organization agent (12 new commands)"
```

---

## Task 12: Update Shared Action Types

**Files:**
- Modify: `packages/types/src/actions.ts`

- [ ] **Step 1: Add organization action types to DawActionType**

In `packages/types/src/actions.ts`, update the `DawActionType` union to include the new actions:

```typescript
export type DawActionType =
  | "set_bpm"
  | "get_state"
  | "get_project_state"
  | "get_pattern_notes"
  | "add_track"
  | "remove_track"
  | "set_track_volume"
  | "set_track_pan"
  | "set_track_mute"
  | "set_track_solo"
  | "rename_track"
  | "play"
  | "stop"
  | "record"
  // Organization actions
  | "rename_channel"
  | "set_channel_color"
  | "set_channel_insert"
  | "rename_mixer_track"
  | "set_mixer_track_color"
  | "rename_playlist_track"
  | "set_playlist_track_color"
  | "group_playlist_tracks"
  | "rename_pattern"
  | "set_pattern_color";
```

- [ ] **Step 2: Commit**

```bash
git add packages/types/src/actions.ts
git commit -m "feat: add organization action types to shared DawActionType"
```

---

## Task 13: Register Bridge Handlers for WebSocket Path

**Files:**
- Modify: `bridge/core/actions.py` (no changes needed — it's dynamic)
- Modify: `bridge/fl_studio/handlers.py`

The `ActionRouter` in `bridge/core/actions.py` already supports dynamic registration. We just need to register the new handlers in the FL Studio handler registration function.

- [ ] **Step 1: Add organization handlers to register_fl_handlers**

In `bridge/fl_studio/handlers.py`, add the import and registration at the end of `register_fl_handlers`:

```python
from bridge.fl_studio.handlers_organize import ORGANIZE_HANDLERS
```

Then update `register_fl_handlers`:

```python
def register_fl_handlers(router) -> None:
    router.register("set_bpm", handle_set_bpm)
    router.register("get_state", handle_get_state)
    router.register("add_track", handle_add_track)
    router.register("play", handle_play)
    router.register("stop", handle_stop)
    router.register("record", handle_record)
    router.register("set_track_volume", handle_set_track_volume)
    router.register("set_track_pan", handle_set_track_pan)
    router.register("set_track_mute", handle_set_track_mute)
    router.register("set_track_solo", handle_set_track_solo)
    router.register("rename_track", handle_rename_track)
    # Organization handlers
    for action_name, handler in ORGANIZE_HANDLERS.items():
        router.register(action_name, handler)
```

- [ ] **Step 2: Commit**

```bash
git add bridge/fl_studio/handlers.py
git commit -m "feat: register organization handlers in bridge ActionRouter"
```

---

## Task 14: Add ANTHROPIC_API_KEY Environment Variable

**Files:**
- Modify: `apps/web/.env.local` (or `.env`)

- [ ] **Step 1: Add the environment variable**

Add to `apps/web/.env.local`:

```
ANTHROPIC_API_KEY=your-api-key-here
```

The `@ai-sdk/anthropic` provider reads `ANTHROPIC_API_KEY` from the environment by default — no code configuration needed.

- [ ] **Step 2: Verify .gitignore excludes .env files**

Run:
```bash
grep -r "\.env" /Users/cristiancirje/Desktop/Dev/studio-ai/.gitignore
```
Expected: `.env*` or `.env.local` is listed.

- [ ] **Step 3: No commit** (env files should not be committed)

---

## Task 15: Verify TypeScript Compilation

**Files:** None (verification only)

- [ ] **Step 1: Run TypeScript compiler**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web && pnpm exec tsc --noEmit
```
Expected: No errors. If there are errors, fix them in the relevant files.

- [ ] **Step 2: Run the dev server to check for runtime issues**

Run:
```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai && pnpm dev
```
Expected: Dev server starts without errors. Ctrl+C to stop.

---

## Task 16: Manual Integration Test Checklist

This task is for manual verification once the FL Studio plugin and bridge are running.

- [ ] **Step 1: Test the analyze endpoint**

```bash
curl -X POST http://localhost:3000/api/ai/organize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_PLUGIN_TOKEN" \
  -d '{"action": "analyze"}'
```
Expected: JSON response with `aiPlan`, `plan` (with preview groups and actions), and `projectState`.

- [ ] **Step 2: Test the scaffold endpoint**

```bash
curl -X POST http://localhost:3000/api/ai/organize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_PLUGIN_TOKEN" \
  -d '{"action": "scaffold", "genre": "trap beat"}'
```
Expected: JSON response with template plan containing drums, bass, leads, etc.

- [ ] **Step 3: Test the adjust endpoint**

Use the `aiPlan` from step 1 or 2:

```bash
curl -X POST http://localhost:3000/api/ai/organize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_PLUGIN_TOKEN" \
  -d '{"action": "adjust", "plan": <aiPlan from above>, "feedback": "move channel 0 to pads", "projectState": <projectState from above>}'
```
Expected: Updated plan with the requested change.

- [ ] **Step 4: Test the execute endpoint**

```bash
curl -X POST http://localhost:3000/api/ai/organize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_PLUGIN_TOKEN" \
  -d '{"action": "execute", "plan": <aiPlan>, "channelCount": <N>, "projectState": <projectState>}'
```
Expected: Execution result with completedActions count. Check FL Studio to verify channels are renamed and colored.
