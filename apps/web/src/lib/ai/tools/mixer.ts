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
  };
}
