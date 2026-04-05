import { generateText, Output } from "ai";
import { google } from "@ai-sdk/google";
import { aiPlanSchema } from "./types";
import { ORGANIZATION_SYSTEM_PROMPT, SCAFFOLD_SYSTEM_PROMPT } from "./prompts";
import type { AIPlan, ProjectMap, EnhancedProjectState } from "@studio-ai/types";

export async function runOrganization(
  projectMap: ProjectMap,
  projectState: EnhancedProjectState,
): Promise<AIPlan> {
  const { output } = await generateText({
    model: google("gemini-2.5-flash"),
    output: Output.object({ schema: aiPlanSchema }),
    system: ORGANIZATION_SYSTEM_PROMPT,
    prompt: `Project map:\n${JSON.stringify(projectMap, null, 2)}\n\nCurrent project state (${projectState.channels.length} channels, ${projectState.mixer_tracks.length} mixer tracks):\n${JSON.stringify({ channels: projectState.channels, mixer_tracks: projectState.mixer_tracks }, null, 2)}\n\nAssign names and role groups for every channel. Fix any unrouted channels.`,
  });

  if (!output) {
    throw new Error("Organization agent did not produce a plan");
  }

  return output as AIPlan;
}

export async function runScaffold(genreDescription: string): Promise<AIPlan> {
  const { output } = await generateText({
    model: google("gemini-2.5-flash"),
    output: Output.object({ schema: aiPlanSchema }),
    system: SCAFFOLD_SYSTEM_PROMPT,
    prompt: `Create a project template for: ${genreDescription}\n\nGenerate channelAssignments starting from index 0. Leave routingFixes empty (new projects have no existing routing to fix — channels will be auto-routed by index).`,
  });

  if (!output) {
    throw new Error("Scaffold agent did not produce a plan");
  }

  return output as AIPlan;
}

export async function adjustPlan(
  currentPlan: AIPlan,
  userFeedback: string,
): Promise<AIPlan> {
  const { output } = await generateText({
    model: google("gemini-2.5-flash"),
    output: Output.object({ schema: aiPlanSchema }),
    system: ORGANIZATION_SYSTEM_PROMPT,
    prompt: `Current plan:\n${JSON.stringify(currentPlan, null, 2)}\n\nUser feedback: "${userFeedback}"\n\nUpdate the plan based on the feedback. Return the complete updated plan (all channels, not just changed ones).`,
  });

  if (!output) {
    throw new Error("Plan adjustment did not produce output");
  }

  return output as AIPlan;
}
