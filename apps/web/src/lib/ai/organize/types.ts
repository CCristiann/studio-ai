import { z } from "zod";

export const roleGroupSchema = z.enum([
  "drums", "bass", "leads", "pads", "fx", "vocals", "other",
]);

export const projectMapSchema = z.object({
  channels: z.array(z.object({
    index: z.number(),
    currentName: z.string(),
    plugin: z.string(),
    inferredRole: z.string().describe("Specific role like 'kick', 'snare', 'sub-bass', 'lead synth'"),
    roleGroup: roleGroupSchema,
    confidence: z.enum(["high", "medium", "low"]),
    reasoning: z.string().describe("Brief explanation of why this classification was chosen"),
  })),
});

export const aiPlanSchema = z.object({
  channelAssignments: z.array(z.object({
    index: z.number().describe("0-indexed channel index"),
    newName: z.string().max(128).describe("New display name for the channel"),
    roleGroup: roleGroupSchema,
  })),
  routingFixes: z.array(z.object({
    channelIndex: z.number().describe("0-indexed channel that needs routing"),
    assignedInsert: z.number().describe("Mixer insert index to route to"),
  })),
});

export type ProjectMapOutput = z.infer<typeof projectMapSchema>;
export type AIPlanOutput = z.infer<typeof aiPlanSchema>;
