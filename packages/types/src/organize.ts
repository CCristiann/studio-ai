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
