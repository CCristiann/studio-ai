// apps/web/src/lib/ai/tools/project.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description:
        "Snapshot of the FL Studio project: BPM, channels (with plugin identity), " +
        "mixer tracks (with effect-slot counts and routing graph), playlist tracks, " +
        "patterns (with length), current selection, and FL capabilities. " +
        "Call ONCE at the start of any organize task — do NOT re-call within the same " +
        "turn after the user has agreed to a plan; the user agreed to what you summarized, " +
        "not to a re-fetch.",
      inputSchema: z.object({
        include_routing: z
          .boolean()
          .optional()
          .default(true)
          .describe(
            "Include per-mixer-track outbound routing graph. Default true. " +
            "Pass false for a fast cold-start summary, or when a prior call returned " +
            "truncated_sections containing 'routing'.",
          ),
      }),
      toRelay: ({ include_routing }) => ({
        action: "get_project_state",
        params: { include_routing },
      }),
    }),

    undo: relayTool(userId, {
      description:
        "Undo the most recent change in FL Studio (uses FL's native undo history). " +
        "After applying an organization plan, this reverts the entire batch as one step. " +
        "Pass `count` only when a previous `apply_organization_plan` returned " +
        "`undo_grouped: false` — then pass that response's `op_count`.",
      inputSchema: z.object({
        count: z
          .number()
          .int()
          .min(1)
          .max(2000)
          .optional()
          .describe(
            "Number of undo steps. Default 1. Only set when a prior " +
            "apply_organization_plan returned undo_grouped:false.",
          ),
      }),
      toRelay: ({ count }) => ({
        action: "undo",
        params: count !== undefined ? { count } : {},
      }),
    }),
  };
}
