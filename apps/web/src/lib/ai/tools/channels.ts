import { z } from "zod";
import { relayTool } from "./_shared";

const CH_INDEX = z.number().int().min(0).max(999).describe("Channel rack index (0-indexed)");

export function channelTools(userId: string) {
  return {
    set_channel_volume: relayTool(userId, {
      description: "Set a channel rack entry's volume (0.0 to 1.0, where ~0.78 is unity).",
      inputSchema: z.object({
        index: CH_INDEX,
        volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
      }),
      toRelay: ({ index, volume }) => ({
        action: "set_channel_volume",
        params: { index, volume },
      }),
    }),

    set_channel_pan: relayTool(userId, {
      description: "Set a channel rack entry's stereo pan (-1.0 = hard left, 0 = center, 1.0 = hard right).",
      inputSchema: z.object({
        index: CH_INDEX,
        pan: z.number().min(-1).max(1).describe("Pan (-1.0 to 1.0)"),
      }),
      toRelay: ({ index, pan }) => ({
        action: "set_channel_pan",
        params: { index, pan },
      }),
    }),

    set_channel_enabled: relayTool(userId, {
      description: "Enable or disable (mute) a channel rack entry.",
      inputSchema: z.object({
        index: CH_INDEX,
        enabled: z.boolean().describe("true to enable, false to mute"),
      }),
      toRelay: ({ index, enabled }) => ({
        action: "set_channel_enabled",
        params: { index, enabled },
      }),
    }),
  };
}
