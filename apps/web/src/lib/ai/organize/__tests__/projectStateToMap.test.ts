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

  it("formats empty-name plugin as '(type_label)' without leading space", () => {
    // Spec §10: sampler channel with no instrument loaded sends
    // { name: "", type: 0, type_label: "sampler" }
    const state = baseState();
    state.channels = [{
      index: 0, name: "Channel 1", color: 0, volume: 0.78, pan: 0, enabled: true, insert: 1,
      plugin: { name: "", type: 0, type_label: "sampler" },
    }];
    const map = projectStateToMap(state);
    expect(map.channels[0].plugin).toBe("(sampler)");
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
