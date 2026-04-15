import { z } from "zod";
import { relayTool } from "./_shared";

const MX_INDEX = z.number().int().min(0).max(126).describe("Mixer track index (0=Master, 1-125=Inserts, 126=Current)");

export function mixerTools(userId: string) {
  return {
    set_track_volume: relayTool(userId, {
      description: "Set a mixer track's volume level.",
      inputSchema: z.object({
        index: MX_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({
        action: "set_track_volume",
        params: { index, volume },
      }),
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
  };
}
