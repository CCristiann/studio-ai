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
