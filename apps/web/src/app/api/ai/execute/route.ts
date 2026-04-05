import { streamText, tool, stepCountIs, UIMessage, convertToModelMessages } from "ai";
import { google } from "@ai-sdk/google";
import { z } from "zod";
import { auth } from "@/lib/auth";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { rateLimit } from "@/lib/rate-limit";
import { relay, RelayError } from "@/lib/relay";
import { runAnalysis } from "@/lib/ai/organize/analysis-agent";
import { runOrganization, runScaffold, adjustPlan } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { executePlan, validateStateBeforeExecution } from "@/lib/ai/organize/execute-plan";
import type { AIPlan, EnhancedProjectState } from "@studio-ai/types";

async function getUserId(req: Request): Promise<string | null> {
  // 1. Try Bearer token (plugin WebView)
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  // 2. Fall back to session cookie (browser dashboard)
  const session = await auth();
  return session?.userId ?? null;
}

export async function POST(req: Request) {
  const userId = await getUserId(req);
  if (!userId) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Rate limit: max 20 AI requests per user per minute
  const { success } = rateLimit(`ai:${userId}`, {
    limit: 20,
    windowMs: 60_000,
  });
  if (!success) {
    return new Response("Rate limit exceeded", { status: 429 });
  }

  const { messages }: { messages: UIMessage[] } = await req.json();

  const result = streamText({
    model: google("gemini-2.5-flash"),
    system: `You are Studio AI, an AI assistant that controls FL Studio through natural language.

You can:
- Set BPM, add tracks, control playback, adjust mixer volumes
- Organize existing projects: analyze channels, classify them by role (drums, bass, leads, pads, fx, vocals), then rename and color-code everything consistently
- Scaffold new projects: set up a genre-specific template with named, color-coded channels

When the user asks to organize or clean up their project, use organize_project with confirm=false first to show a preview, then confirm=true to apply.
When the user wants to start a new beat/track, use scaffold_project with the genre they describe — preview first, then apply.

Always present the preview clearly to the user before applying changes. Format the preview as a grouped list showing the color groups and channel names.`,
    messages: await convertToModelMessages(messages),
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

      organize_project: tool({
        description: "Analyze and organize the current FL Studio project. Reads the project state, classifies channels by musical role (drums, bass, leads, pads, fx, vocals), then renames and color-codes everything consistently. Shows a preview before applying. Use when the user asks to organize, clean up, or color-code their project.",
        inputSchema: z.object({
          confirm: z.boolean().default(false).describe("Set to true to apply the plan after previewing. First call with false to preview, then true to apply."),
        }),
        execute: async (input) => {
          try {
            if (!input.confirm) {
              // Stage 1 + 2: Analyze and generate plan preview
              const { projectMap, projectState } = await runAnalysis(userId);
              const aiPlan = await runOrganization(projectMap, projectState);
              const fullPlan = expandPlan(aiPlan, projectState);

              // Store plan in response for the AI to present to user
              return {
                success: true,
                status: "preview",
                preview: fullPlan.preview,
                actionCount: fullPlan.actions.length,
                _aiPlan: aiPlan,
                _projectState: projectState,
              };
            } else {
              // Execute: re-analyze and apply (stateless — no server-side plan storage)
              const { projectMap, projectState } = await runAnalysis(userId);
              const aiPlan = await runOrganization(projectMap, projectState);
              const fullPlan = expandPlan(aiPlan, projectState);
              const result = await executePlan(userId, fullPlan);

              return {
                success: result.failures.length === 0,
                status: "applied",
                completedActions: result.completedActions,
                totalActions: result.totalActions,
                failures: result.failures.length > 0
                  ? result.failures.map(f => `${f.action.type}(${JSON.stringify(f.action.params)}): ${f.error}`)
                  : undefined,
              };
            }
          } catch (e) {
            return { success: false, error: e instanceof Error ? e.message : "Organization failed" };
          }
        },
      }),

      scaffold_project: tool({
        description: "Set up a new FL Studio project template based on a genre or style. Creates named, color-coded channels with proper routing. Use when the user says they're starting a new beat/track and mentions a genre or style (e.g., 'start a trap beat', 'new lo-fi project', 'set up a house track').",
        inputSchema: z.object({
          genre: z.string().describe("Genre or style description, e.g. 'trap beat', 'lo-fi hip hop', 'dark drill with 808s'"),
          confirm: z.boolean().default(false).describe("Set to true to apply the template after previewing."),
        }),
        execute: async (input) => {
          try {
            const aiPlan = await runScaffold(input.genre);

            // Build synthetic empty state for expansion
            const emptyState: EnhancedProjectState = {
              bpm: 140,
              project_name: "New Project",
              channels: aiPlan.channelAssignments.map((a, i) => ({
                index: i, name: `Channel ${i + 1}`, plugin: "Sampler",
                color: 0, volume: 0.8, pan: 0, enabled: true, insert: i + 1,
              })),
              mixer_tracks: aiPlan.channelAssignments.map((a, i) => ({
                index: i + 1, name: `Insert ${i + 1}`, color: 0,
                volume: 0.8, pan: 0, muted: false,
              })),
              playlist_tracks: [],
              patterns: aiPlan.channelAssignments.map((a, i) => ({
                index: i + 1, name: `Pattern ${i + 1}`, color: 0,
              })),
            };

            const fullPlan = expandPlan(aiPlan, emptyState);

            if (!input.confirm) {
              return {
                success: true,
                status: "preview",
                genre: input.genre,
                preview: fullPlan.preview,
                actionCount: fullPlan.actions.length,
              };
            } else {
              const result = await executePlan(userId, fullPlan);
              return {
                success: result.failures.length === 0,
                status: "applied",
                genre: input.genre,
                completedActions: result.completedActions,
                totalActions: result.totalActions,
                failures: result.failures.length > 0
                  ? result.failures.map(f => `${f.action.type}(${JSON.stringify(f.action.params)}): ${f.error}`)
                  : undefined,
              };
            }
          } catch (e) {
            return { success: false, error: e instanceof Error ? e.message : "Scaffold failed" };
          }
        },
      }),
    },
    stopWhen: stepCountIs(5),
  });

  return result.toUIMessageStreamResponse();
}
