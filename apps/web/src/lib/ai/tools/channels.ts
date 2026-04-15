// apps/web/src/lib/ai/tools/channels.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const CH_INDEX = z.number().int().min(0).max(999).describe("Channel rack index (0-indexed)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF).describe("24-bit RGB color (e.g. 0xFF0000 = red)");

export function channelTools(userId: string) {
  return {
    rename_channel: relayTool(userId, {
      description: "Rename a single channel rack entry. For renaming many channels at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: CH_INDEX,
        name: z.string().min(1).max(128).describe("New name (1-128 chars)"),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_channel", params: { index, name } }),
    }),

    set_channel_color: relayTool(userId, {
      description: "Set the color of a single channel rack entry (24-bit RGB). For coloring many at once, prefer apply_organization_plan.",
      inputSchema: z.object({ index: CH_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_channel_color", params: { index, color } }),
    }),

    set_channel_insert: relayTool(userId, {
      description: "Route a channel rack entry to a mixer insert.",
      inputSchema: z.object({
        index: CH_INDEX,
        insert: z.number().int().min(0).max(126).describe("Mixer insert track (0=Master, 1-125=Inserts, 126=Current)"),
      }),
      toRelay: ({ index, insert }) => ({ action: "set_channel_insert", params: { index, insert } }),
    }),

    set_channel_volume: relayTool(userId, {
      description: "Set a channel rack entry's volume (0.0 to 1.0, where ~0.78 is unity).",
      inputSchema: z.object({
        index: CH_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({ action: "set_channel_volume", params: { index, volume } }),
    }),

    set_channel_pan: relayTool(userId, {
      description: "Set a channel rack entry's stereo pan (-1.0 = hard left, 0 = center, 1.0 = hard right).",
      inputSchema: z.object({
        index: CH_INDEX,
        pan: z.number().min(-1).max(1).describe("Pan (-1.0 to 1.0)"),
      }),
      toRelay: ({ index, pan }) => ({ action: "set_channel_pan", params: { index, pan } }),
    }),

    set_channel_enabled: relayTool(userId, {
      description: "Enable or disable (mute) a channel rack entry.",
      inputSchema: z.object({
        index: CH_INDEX,
        enabled: z.boolean().describe("true to enable, false to mute"),
      }),
      toRelay: ({ index, enabled }) => ({ action: "set_channel_enabled", params: { index, enabled } }),
    }),

    find_channel_by_name: relayTool(userId, {
      description: "Find channel rack entries by name (fuzzy substring match). Returns up to `limit` matches sorted by score. Use this to resolve user references like \"the kick\" before calling per-channel setters.",
      inputSchema: z.object({
        query: z.string().min(1).max(128).describe("Substring to search for (case-insensitive)"),
        limit: z.number().int().min(1).max(20).optional().default(5).describe("Max matches to return"),
      }),
      toRelay: ({ query, limit }) => ({ action: "find_channel_by_name", params: { query, limit } }),
    }),
  };
}
