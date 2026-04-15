import { tool } from "ai";
import { z } from "zod";
import { relay } from "@/lib/relay";
import { relayTool } from "./_shared";
import { runAnalysis } from "@/lib/ai/organize/analysis-agent";
import { runOrganization, runScaffold } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { executePlan } from "@/lib/ai/organize/execute-plan";
import type { EnhancedProjectState } from "@studio-ai/types";

export function organizeTools(userId: string) {
  return {
    apply_organization_plan: relayTool(userId, {
      description: "Apply a structured rename + recolor + (channel only) insert-routing plan in a single FL Studio undo step. Use this for any organize task that touches more than 3 entities — it's one round-trip and one Ctrl+Z to revert. Each section is optional; omit sections you don't need to touch. Item fields are independent (you can pass name, color, or both). The whole apply registers as one undo step. If the response has `undo_grouped: false`, then `undo` must be called with `count: <op_count>` to fully revert.",
      inputSchema: z.object({
        channels: z.array(z.object({
          index: z.number().int().min(0).max(999).describe("0-indexed channel rack entry"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
          insert: z.number().int().min(0).max(126).optional().describe("Target mixer insert"),
        })).optional(),
        mixer_tracks: z.array(z.object({
          index: z.number().int().min(0).max(126).describe("0-indexed mixer track (0=Master, 1-125=Inserts, 126=Current)"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
        playlist_tracks: z.array(z.object({
          index: z.number().int().min(1).max(500).describe("1-indexed playlist track"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
        patterns: z.array(z.object({
          index: z.number().int().min(1).max(999).describe("1-indexed pattern"),
          name:  z.string().min(1).max(128).optional(),
          color: z.number().int().min(0).max(0xFFFFFF).optional(),
        })).optional(),
      }),
      toRelay: (plan) => ({ action: "apply_organization_plan", params: plan }),
    }),

    organize_project: tool({
      description: "Analyze and organize the current FL Studio project. Reads the project state, classifies channels by musical role (drums, bass, leads, pads, fx, vocals), then renames and color-codes everything consistently. Shows a preview before applying. Use when the user asks to organize, clean up, or color-code their project.",
      inputSchema: z.object({
        confirm: z.boolean().default(false).describe("Set to true to apply the plan after previewing. First call with false to preview, then true to apply."),
      }),
      execute: async (input) => {
        try {
          if (!input.confirm) {
            const { projectMap, projectState } = await runAnalysis(userId);
            const aiPlan = await runOrganization(projectMap, projectState);
            const fullPlan = expandPlan(aiPlan, projectState);
            return {
              success: true,
              status: "preview",
              preview: fullPlan.preview,
              actionCount: fullPlan.actions.length,
              _aiPlan: aiPlan,
              _projectState: projectState,
            };
          } else {
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
      description: "Set up a new FL Studio project template based on a genre or style. Renames and color-codes the existing channels in the project to match the genre. Note: FL Studio cannot add channels programmatically, so the template is limited to the number of channels already in the project. Use when the user says they're starting a new beat/track and mentions a genre or style.",
      inputSchema: z.object({
        genre: z.string().describe("Genre or style description, e.g. 'trap beat', 'lo-fi hip hop', 'dark drill with 808s'"),
        confirm: z.boolean().default(false).describe("Set to true to apply the template after previewing."),
      }),
      execute: async (input) => {
        try {
          const stateResult = await relay(userId, "get_project_state", {});
          if (!stateResult.success) {
            return { success: false, error: "Could not read project state" };
          }
          const projectState = stateResult.data as EnhancedProjectState | undefined;
          if (!projectState?.channels) {
            return { success: false, error: "Project state is empty — open a project with channels in the Channel Rack." };
          }
          const channelCount = projectState.channels.length;

          const aiPlan = await runScaffold(input.genre);
          const trimmedPlan = {
            ...aiPlan,
            channelAssignments: aiPlan.channelAssignments
              .slice(0, channelCount)
              .map((a, i) => ({ ...a, index: projectState.channels[i].index })),
          };

          const fullPlan = expandPlan(trimmedPlan, projectState);

          if (!input.confirm) {
            const skipped = aiPlan.channelAssignments.length - trimmedPlan.channelAssignments.length;
            return {
              success: true,
              status: "preview",
              genre: input.genre,
              preview: fullPlan.preview,
              actionCount: fullPlan.actions.length,
              channelsAvailable: channelCount,
              channelsRequested: aiPlan.channelAssignments.length,
              ...(skipped > 0 && {
                note: `Your project has ${channelCount} channels but the template needs ${aiPlan.channelAssignments.length}. ${skipped} channels were skipped. Add more channels in FL Studio first if you want the full template.`,
              }),
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
  };
}
