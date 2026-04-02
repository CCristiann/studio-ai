import { streamText, tool, stepCountIs } from "ai";
import { google } from "@ai-sdk/google";
import { z } from "zod";
import { auth } from "@/lib/auth";
import { relay, RelayError } from "@/lib/relay";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.userId) {
    return new Response("Unauthorized", { status: 401 });
  }

  const { messages } = await req.json();
  const userId = session.userId;

  const result = streamText({
    model: google("gemini-2.0-flash"),
    system: `You are Studio AI, an AI assistant that controls Digital Audio Workstations (DAWs) through natural language. You can set BPM, add tracks, get project state, and control playback. When the user asks you to do something in their DAW, use the appropriate tool. Always confirm what you did after executing a command.`,
    messages,
    tools: {
      set_bpm: tool({
        description: "Set the BPM (tempo) of the current project. Valid range: 10-999.",
        inputSchema: z.object({
          bpm: z.number().min(10).max(999).describe("The BPM to set"),
        }),
        execute: async (input) => {
          const { bpm } = input;
          try {
            const result = await relay(userId, "set_bpm", { bpm });
            return result.success
              ? { success: true, bpm }
              : { success: false, error: result.error };
          } catch (e) {
            if (e instanceof RelayError) {
              return { success: false, error: e.message, code: e.code };
            }
            return { success: false, error: "Failed to relay command" };
          }
        },
      }),

      get_project_state: tool({
        description: "Get the current state of the DAW project including BPM, tracks, and project name.",
        inputSchema: z.object({}),
        execute: async () => {
          try {
            const result = await relay(userId, "get_state", {});
            return result.success
              ? { success: true, data: result.data }
              : { success: false, error: result.error };
          } catch (e) {
            if (e instanceof RelayError) {
              return { success: false, error: e.message, code: e.code };
            }
            return { success: false, error: "Failed to relay command" };
          }
        },
      }),

      add_track: tool({
        description: "Add a new track to the project.",
        inputSchema: z.object({
          name: z.string().describe("Name for the new track"),
          type: z.enum(["audio", "midi"]).describe("Type of track to add"),
        }),
        execute: async (input) => {
          const { name, type } = input;
          try {
            const result = await relay(userId, "add_track", { name, type });
            return result.success
              ? { success: true, data: result.data }
              : { success: false, error: result.error };
          } catch (e) {
            if (e instanceof RelayError) {
              return { success: false, error: e.message, code: e.code };
            }
            return { success: false, error: "Failed to relay command" };
          }
        },
      }),

      play: tool({
        description: "Start playback in the DAW.",
        inputSchema: z.object({}),
        execute: async () => {
          try {
            const result = await relay(userId, "play", {});
            return result.success
              ? { success: true }
              : { success: false, error: result.error };
          } catch (e) {
            if (e instanceof RelayError) {
              return { success: false, error: e.message, code: e.code };
            }
            return { success: false, error: "Failed to relay command" };
          }
        },
      }),

      stop: tool({
        description: "Stop playback in the DAW.",
        inputSchema: z.object({}),
        execute: async () => {
          try {
            const result = await relay(userId, "stop", {});
            return result.success
              ? { success: true }
              : { success: false, error: result.error };
          } catch (e) {
            if (e instanceof RelayError) {
              return { success: false, error: e.message, code: e.code };
            }
            return { success: false, error: "Failed to relay command" };
          }
        },
      }),

      set_track_volume: tool({
        description: "Set a mixer track's volume level.",
        inputSchema: z.object({
          index: z.number().int().min(0).describe("Mixer track index"),
          volume: z.number().min(0).max(1).describe("Volume level (0.0 to 1.0)"),
        }),
        execute: async (input) => {
          const { index, volume } = input;
          try {
            const result = await relay(userId, "set_track_volume", { index, volume });
            return result.success
              ? { success: true, data: result.data }
              : { success: false, error: result.error };
          } catch (e) {
            if (e instanceof RelayError) {
              return { success: false, error: e.message, code: e.code };
            }
            return { success: false, error: "Failed to relay command" };
          }
        },
      }),
    },
    stopWhen: stepCountIs(5),
  });

  return result.toUIMessageStreamResponse();
}
