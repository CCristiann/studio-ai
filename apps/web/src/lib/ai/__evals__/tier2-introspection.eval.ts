/**
 * Local-only AI eval for tier 2 introspection.
 *
 * Run via: bunx vitest run apps/web/src/lib/ai/__evals__/tier2-introspection.eval.ts
 *
 * Requires GEMINI_API_KEY (or whatever provider key the chat agent uses).
 * Skipped automatically when the key is absent — DO NOT block CI on this.
 *
 * What this verifies (per spec §11.3): the AI's TEXT response USES the new
 * project-state fields. Tool-selection evals can pass while content regresses
 * to generic replies; these substring assertions close that gap.
 *
 * Deviations from plan snippet:
 * - `convertToModelMessages` takes UIMessage[] (with `id`, `role`, `parts`,
 *   `metadata`) not CoreMessage[], per AI SDK v6 actual signature.
 * - The `messages` arg is awaited directly (no `as never` cast needed).
 * - `providerOptions` mirrors the chat route for thinkingBudget: 0.
 */
import { describe, it, expect } from "vitest";
import { streamText, convertToModelMessages, stepCountIs, tool } from "ai";
import { google } from "@ai-sdk/google";
import { z } from "zod";
import { SYSTEM_PROMPT } from "../system-prompt";

// Skip when no API key — keeps CI green.
const SKIP = !process.env.GEMINI_API_KEY;

// Fixture project state matching the EnhancedProjectState shape.
const fixture = {
  bpm: 128,
  project_name: "EvalProj",
  playing: false,
  channels: [
    { index: 0,  name: "Kick",   color: 0xFF0000, volume: 0.78, pan: 0,    enabled: true, insert: 1,  plugin: { name: "Sampler", type: 0, type_label: "sampler" } },
    { index: 5,  name: "Lead",   color: 0x00FF00, volume: 0.6,  pan: 0,    enabled: true, insert: 9,  plugin: { name: "Sytrus",  type: 2, type_label: "vst" } },
    { index: 12, name: "Pad",    color: 0x0000FF, volume: 0.5,  pan: 0,    enabled: true, insert: 11, plugin: { name: "FLEX",    type: 2, type_label: "vst" } },
  ],
  mixer_tracks: [
    { index: 0,  name: "Master", color: 0,        volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [] },
    { index: 1,  name: "Kick",   color: 0,        volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [{ to_index: 7 }] },
    { index: 2,  name: "Snare",  color: 0,        volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [{ to_index: 7 }] },
    { index: 3,  name: "Hat",    color: 0,        volume: 0.8, pan: 0, muted: false, slot_count: 0, routes_to: [{ to_index: 7 }] },
    { index: 7,  name: "DRUMS",  color: 0xFF0000, volume: 0.8, pan: 0, muted: false, slot_count: 4, routes_to: [] },
    { index: 22, name: "Vocal",  color: 0xD53F8C, volume: 0.7, pan: 0, muted: false, slot_count: 6, routes_to: [{ to_index: 88 }] },
  ],
  playlist_tracks: [],
  patterns: [],
  selection: { channel_index: null, pattern_index: null, mixer_track_index: null },
  capabilities: {
    fl_version: "21.2.3", api_version: 36,
    has_send_levels: true, has_eq_getters: true, has_save_undo: true,
    has_pattern_length: true, has_slot_color: true,
  },
  snapshot_at: 0,
};

// Custom tools dict for the eval. Bypasses the relay entirely.
function evalTools() {
  return {
    get_project_state: tool({
      description: "Get FL Studio project state (eval fixture).",
      inputSchema: z.object({
        include_routing: z.boolean().optional().default(true),
      }),
      execute: async () => ({ success: true, data: fixture }),
    }),
    get_mixer_chain: tool({
      description: "Get effect chain for a mixer track (eval fixture).",
      inputSchema: z.object({ index: z.number().int().min(0).max(126) }),
      execute: async ({ index }: { index: number }) => {
        if (index === 0) {
          return { success: true, data: { index: 0, slots_enabled: true, slots: [
            { slot_index: 0, plugin_name: "Fruity Limiter" },
            { slot_index: 1, plugin_name: "Youlean Loudness Meter" },
            { slot_index: 2, plugin_name: "Soundgoodizer" },
          ] } };
        }
        if (index === 22) {
          return { success: true, data: { index: 22, slots_enabled: true, slots: [
            { slot_index: 0, plugin_name: "Fruity Limiter" },
            { slot_index: 1, plugin_name: "Pro-DS" },
            { slot_index: 2, plugin_name: "Pro-Q 3" },
            { slot_index: 3, plugin_name: "Pro-C 2" },
          ] } };
        }
        return { success: true, data: { index, slots_enabled: true, slots: [] } };
      },
    }),
    find_mixer_track_by_name: tool({
      description: "Find mixer track by name (eval fixture).",
      inputSchema: z.object({ query: z.string(), limit: z.number().int().min(1).max(20).optional().default(5) }),
      execute: async ({ query }: { query: string }) => {
        const matches = fixture.mixer_tracks
          .filter(t => t.name.toLowerCase().includes(query.toLowerCase()))
          .map(t => ({ index: t.index, name: t.name, score: 0.9 }));
        return { success: true, data: { matches } };
      },
    }),
  };
}

async function runChat(userMsg: string): Promise<string> {
  // Build a UIMessage array (AI SDK v6 format with id/role/parts/metadata).
  const uiMessages = [
    {
      id: "eval-1",
      role: "user" as const,
      parts: [{ type: "text" as const, text: userMsg }],
      metadata: {},
    },
  ];

  const result = streamText({
    model: google("gemini-2.5-flash"),
    providerOptions: {
      google: { thinkingConfig: { thinkingBudget: 0 } },
    },
    system: SYSTEM_PROMPT,
    messages: await convertToModelMessages(uiMessages),
    tools: evalTools(),
    stopWhen: stepCountIs(5),
  });

  let fullText = "";
  for await (const chunk of result.textStream) {
    fullText += chunk;
  }
  return fullText;
}

describe.skipIf(SKIP)("tier 2 response-content evals", () => {
  it("'what synths am I using?' mentions Sytrus and FLEX", async () => {
    const reply = await runChat("What synths am I using?");
    expect(reply).toMatch(/sytrus/i);
    expect(reply).toMatch(/flex/i);
  }, 60_000);

  it("'where's my drum bus?' mentions Insert 7 or DRUMS", async () => {
    const reply = await runChat("Where's my drum bus?");
    expect(reply).toMatch(/insert\s*7|drums/i);
  }, 60_000);

  it("'tell me about insert 22' mentions slot count", async () => {
    const reply = await runChat("Tell me about insert 22");
    expect(reply).toMatch(/\b6\b\s*(slot|plugin|effect|insert)/i);
  }, 60_000);
});
