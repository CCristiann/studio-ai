import { ToolLoopAgent, tool, Output, stepCountIs } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { z } from "zod";
import { relay } from "@/lib/relay";
import { projectMapSchema } from "./types";
import { ANALYSIS_SYSTEM_PROMPT } from "./prompts";
import type { ProjectMap, EnhancedProjectState } from "@repo/types";

export async function runAnalysis(userId: string): Promise<{
  projectMap: ProjectMap;
  projectState: EnhancedProjectState;
}> {
  let capturedState: EnhancedProjectState | null = null;

  const agent = new ToolLoopAgent({
    model: anthropic("claude-sonnet-4-5-20250514"),
    instructions: ANALYSIS_SYSTEM_PROMPT,
    tools: {
      get_project_state: tool({
        description: "Get the full FL Studio project state including all channels, mixer tracks, playlist tracks, and patterns with their names, colors, and routing.",
        inputSchema: z.object({}),
        execute: async () => {
          const result = await relay(userId, "get_project_state", {});
          if (result.success) {
            capturedState = result.data as EnhancedProjectState;
          }
          return result.success
            ? { success: true, data: result.data }
            : { success: false, error: result.error };
        },
      }),
      get_pattern_notes: tool({
        description: "Get MIDI notes from a specific channel in a pattern. Use this to analyze note ranges, rhythmic patterns, and velocity to infer instrument roles when the channel name and plugin are ambiguous.",
        inputSchema: z.object({
          channel_index: z.number().describe("0-indexed channel in channel rack"),
          pattern_index: z.number().optional().describe("1-indexed pattern, defaults to 1"),
        }),
        execute: async (params) => {
          const result = await relay(userId, "get_pattern_notes", {
            channel_index: params.channel_index,
            pattern_index: params.pattern_index ?? 1,
          });
          return result.success
            ? { success: true, data: result.data }
            : { success: false, error: result.error };
        },
      }),
    },
    output: Output.object({ schema: projectMapSchema }),
    stopWhen: stepCountIs(15),
  });

  const { output } = await agent.generate({
    prompt: "Analyze this FL Studio project. Read the project state, then inspect MIDI data for any channels where the role is ambiguous from the name and plugin alone. Classify every channel by musical role.",
  });

  if (!output) {
    throw new Error("Analysis agent did not produce a project map");
  }

  if (!capturedState) {
    throw new Error("Analysis agent did not call get_project_state");
  }

  return { projectMap: output as ProjectMap, projectState: capturedState };
}
