// apps/web/src/lib/ai/organize/_shared.ts
/**
 * Shared helpers used by both:
 *   - apps/web/src/lib/ai/tools/organize.ts
 *   - apps/web/src/app/api/ai/organize/route.ts
 *
 * Extracted to avoid duplication and to fix a regression where the bulk-apply
 * fold was only mapping channel actions, silently dropping rename_mixer_track,
 * set_mixer_track_color, rename_pattern, and set_pattern_color.
 */

import type {
  EnhancedProjectState,
  OrganizationPlan,
  ProjectMap,
} from "@studio-ai/types";

// ── projectStateToMap ────────────────────────────────────────────────────────

/**
 * Convert an EnhancedProjectState (from get_project_state) into the simpler
 * ProjectMap shape that the organization agent's prompt expects.
 *
 * Role inference is deferred to the organization-agent itself; this function
 * just packages the raw state.
 */
export function projectStateToMap(state: EnhancedProjectState): ProjectMap {
  return {
    channels: state.channels.map((c) => ({
      index: c.index,
      currentName: c.name,
      plugin: c.plugin ? `${c.plugin.name} (${c.plugin.type_label})` : "(unknown)",
      inferredRole: "unknown",
      roleGroup: "other" as const,
      confidence: "low" as const,
      reasoning: "Role deferred to organization-agent",
    })),
  };
}

// ── aiPlanToBulkPlan ─────────────────────────────────────────────────────────

type ChannelEntry    = { index: number; name?: string; color?: number; insert?: number };
type MixerTrackEntry = { index: number; name?: string; color?: number };
type PatternEntry    = { index: number; name?: string; color?: number };

/**
 * Fold an expanded OrganizationPlan into the apply_organization_plan envelope.
 *
 * Walks all 7 action types produced by expandPlan and groups them by target
 * index into the three sections the bridge handler accepts:
 *   channels      — rename_channel | set_channel_color | set_channel_insert
 *   mixer_tracks  — rename_mixer_track | set_mixer_track_color
 *   patterns      — rename_pattern | set_pattern_color
 *
 * Sections that received no actions are omitted from the return value so the
 * bridge doesn't receive empty arrays (it accepts optional sections).
 *
 * playlist_tracks are not produced by expandPlan; that section is never
 * emitted.
 */
export function aiPlanToBulkPlan(fullPlan: OrganizationPlan): {
  channels?: ChannelEntry[];
  mixer_tracks?: MixerTrackEntry[];
  patterns?: PatternEntry[];
} {
  const channelMap    = new Map<number, ChannelEntry>();
  const mixerTrackMap = new Map<number, MixerTrackEntry>();
  const patternMap    = new Map<number, PatternEntry>();

  for (const action of fullPlan.actions) {
    switch (action.type) {
      // ── Channel actions ────────────────────────────────────────────────────
      case "rename_channel": {
        const { index, name } = action.params;
        const entry = channelMap.get(index) ?? { index };
        entry.name = name;
        channelMap.set(index, entry);
        break;
      }
      case "set_channel_color": {
        const { index, color } = action.params;
        const entry = channelMap.get(index) ?? { index };
        entry.color = color;
        channelMap.set(index, entry);
        break;
      }
      case "set_channel_insert": {
        const { index, insert } = action.params;
        const entry = channelMap.get(index) ?? { index };
        entry.insert = insert;
        channelMap.set(index, entry);
        break;
      }
      // ── Mixer track actions ────────────────────────────────────────────────
      case "rename_mixer_track": {
        const { index, name } = action.params;
        const entry = mixerTrackMap.get(index) ?? { index };
        entry.name = name;
        mixerTrackMap.set(index, entry);
        break;
      }
      case "set_mixer_track_color": {
        const { index, color } = action.params;
        const entry = mixerTrackMap.get(index) ?? { index };
        entry.color = color;
        mixerTrackMap.set(index, entry);
        break;
      }
      // ── Pattern actions ────────────────────────────────────────────────────
      case "rename_pattern": {
        const { index, name } = action.params;
        const entry = patternMap.get(index) ?? { index };
        entry.name = name;
        patternMap.set(index, entry);
        break;
      }
      case "set_pattern_color": {
        const { index, color } = action.params;
        const entry = patternMap.get(index) ?? { index };
        entry.color = color;
        patternMap.set(index, entry);
        break;
      }
      // ── Playlist track actions (not produced by expandPlan; ignored) ───────
      case "rename_playlist_track":
      case "set_playlist_track_color":
      case "group_playlist_tracks":
        break;
    }
  }

  return {
    ...(channelMap.size > 0    && { channels:     [...channelMap.values()] }),
    ...(mixerTrackMap.size > 0 && { mixer_tracks: [...mixerTrackMap.values()] }),
    ...(patternMap.size > 0    && { patterns:     [...patternMap.values()] }),
  };
}
