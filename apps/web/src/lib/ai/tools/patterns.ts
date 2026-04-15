// apps/web/src/lib/ai/tools/patterns.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const PAT_INDEX = z.number().int().min(1).max(999).describe("Pattern index (1-indexed)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF);

export function patternTools(userId: string) {
  return {
    rename_pattern: relayTool(userId, {
      description: "Rename a single pattern (1-indexed). For many at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: PAT_INDEX,
        name: z.string().min(1).max(128),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_pattern", params: { index, name } }),
    }),

    set_pattern_color: relayTool(userId, {
      description: "Set the color of a pattern (1-indexed, 24-bit RGB).",
      inputSchema: z.object({ index: PAT_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_pattern_color", params: { index, color } }),
    }),
  };
}
