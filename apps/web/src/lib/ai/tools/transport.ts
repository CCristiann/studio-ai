import { z } from "zod";
import { relayTool } from "./_shared";

export function transportTools(userId: string) {
  return {
    set_bpm: relayTool(userId, {
      description: "Set the BPM (tempo) of the current project. Valid range: 10-999.",
      inputSchema: z.object({
        bpm: z.number().min(10).max(999).describe("The BPM to set"),
      }),
      toRelay: ({ bpm }) => ({ action: "set_bpm", params: { bpm } }),
      mapResult: (_data, { bpm }) => ({ bpm }),
    }),

    play: relayTool(userId, {
      description: "Start playback in the DAW.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "play", params: {} }),
      mapResult: () => ({}),
    }),

    stop: relayTool(userId, {
      description: "Stop playback in the DAW.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "stop", params: {} }),
      mapResult: () => ({}),
    }),

    set_pitch: relayTool(userId, {
      description: "Set the project's master pitch in semitones (-12 to +12). Use when the user asks to transpose the whole project up or down.",
      inputSchema: z.object({
        semitones: z.number().min(-12).max(12).describe("Semitones to transpose (-12 to +12)"),
      }),
      toRelay: ({ semitones }) => ({ action: "set_pitch", params: { semitones } }),
    }),
  };
}
