// apps/web/src/lib/ai/tools/organize.ts
import { tool } from "ai";
import { z } from "zod";
import { relay } from "@/lib/relay";
import { relayTool } from "./_shared";
import { runOrganization, runScaffold } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { projectStateToMap, aiPlanToBulkPlan } from "@/lib/ai/organize/_shared";
import type { EnhancedProjectState } from "@studio-ai/types";

/**
 * Why these tools no longer apply directly:
 *
 * Originally `organize_project` and `scaffold_project` had a `confirm` flag —
 * `false` returned a preview, `true` applied. Problem: each `execute` call
 * re-ran Gemini (`runOrganization` / `runScaffold`), so the plan the user
 * approved in step 1 was *not* the plan that got applied in step 2. The
 * second call generated a fresh, slightly-different plan from scratch.
 *
 * Fix: both tools are now *plan generators*. They always return a structured
 * `plan` field shaped like `apply_organization_plan`'s input. The AI shows
 * the preview, gets confirmation, then calls `apply_organization_plan` with
 * the exact plan returned here. One generation, one apply, no drift.
 *
 * Side benefit: the bridge round-trip moves out of these tools entirely,
 * so they only need `get_project_state` for scaffold's channel-count check.
 */

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
      description: "Generate an AI-suggested organization plan for the current FL Studio project (groupings, names, colors). Returns a `plan` field — show the `preview` to the user, get confirmation, then call `apply_organization_plan` with the returned `plan` to actually apply it. This tool does NOT apply changes itself.",
      inputSchema: z.object({}),
      execute: async () => {
        try {
          const stateResult = await relay(userId, "get_project_state", {});
          if (!stateResult.success) {
            return { success: false, error: stateResult.error ?? "Could not read project state" };
          }
          const projectState = stateResult.data as EnhancedProjectState;
          const projectMap = projectStateToMap(projectState);
          const aiPlan = await runOrganization(projectMap, projectState);
          const fullPlan = expandPlan(aiPlan, projectState);
          const bulkPlan = aiPlanToBulkPlan(fullPlan);
          return {
            success: true,
            status: "ready_to_apply",
            preview: fullPlan.preview,
            actionCount: fullPlan.actions.length,
            plan: bulkPlan,
          };
        } catch (e) {
          return { success: false, error: e instanceof Error ? e.message : "Organization failed" };
        }
      },
    }),

    scaffold_project: tool({
      description: "Generate a starter project template for a given genre (rename + color the existing channels). Returns a `plan` field — show the `preview` to the user, get confirmation, then call `apply_organization_plan` with the returned `plan` to actually apply it. This tool does NOT apply changes itself. Note: FL Studio cannot add channels programmatically, so the template is limited to the channels already in the project.",
      inputSchema: z.object({
        genre: z.string().describe("Genre or style description, e.g. 'trap beat', 'lo-fi hip hop', 'dark drill with 808s'"),
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
          const bulkPlan = aiPlanToBulkPlan(fullPlan);
          const skipped = aiPlan.channelAssignments.length - trimmedPlan.channelAssignments.length;
          return {
            success: true,
            status: "ready_to_apply",
            genre: input.genre,
            preview: fullPlan.preview,
            actionCount: fullPlan.actions.length,
            channelsAvailable: channelCount,
            channelsRequested: aiPlan.channelAssignments.length,
            plan: bulkPlan,
            ...(skipped > 0 && {
              note: `Your project has ${channelCount} channels but the template needs ${aiPlan.channelAssignments.length}. ${skipped} channels were skipped. Add more channels in FL Studio first if you want the full template.`,
            }),
          };
        } catch (e) {
          return { success: false, error: e instanceof Error ? e.message : "Scaffold failed" };
        }
      },
    }),
  };
}
