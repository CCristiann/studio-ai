// apps/web/src/lib/ai/tools/project.ts
import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description: "Get the current state of the DAW project including BPM, tracks, and project name. Use this once at the start of any organize task to learn the project layout.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "get_project_state", params: {} }),
    }),

    save_project: relayTool(userId, {
      description: "Save the current FL Studio project. Use this as a checkpoint before bulk-organizing so the user can recover if they dislike the result.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "save_project", params: {} }),
    }),

    undo: relayTool(userId, {
      description: "Undo the most recent change in FL Studio (uses FL's native undo history). After applying an organization plan, this reverts the entire batch as one step. Pass `count` only when a previous `apply_organization_plan` returned `undo_grouped: false` — then pass that response's `op_count`.",
      inputSchema: z.object({
        count: z.number().int().min(1).max(2000).optional().describe("Number of undo steps. Default 1. Only set when a prior apply_organization_plan returned undo_grouped:false."),
      }),
      toRelay: ({ count }) => ({ action: "undo", params: count !== undefined ? { count } : {} }),
    }),
  };
}
