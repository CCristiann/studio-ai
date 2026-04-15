import { tool } from "ai";
import type { ZodTypeAny, z } from "zod";
import { relay, RelayError } from "@/lib/relay";

export interface RelayToolDef<TInput extends ZodTypeAny> {
  description: string;
  inputSchema: TInput;
  /** Map AI tool input → relay action name + params. */
  toRelay: (input: z.infer<TInput>) => { action: string; params: Record<string, unknown> };
  /** Optionally transform the relay's data before returning to the AI. */
  mapResult?: (data: unknown, input: z.infer<TInput>) => unknown;
}

/**
 * Wrap an FL-bridge relay call as a Vercel AI SDK tool.
 *
 * Centralizes the success/RelayError/unknown-error response shape so every
 * tool returns the same `{ success, data?, error?, code? }` envelope.
 */
export function relayTool<TInput extends ZodTypeAny>(
  userId: string,
  def: RelayToolDef<TInput>,
) {
  return tool({
    description: def.description,
    inputSchema: def.inputSchema,
    execute: async (input: z.infer<TInput>) => {
      const { action, params } = def.toRelay(input);
      try {
        const result = await relay(userId, action, params);
        if (!result.success) {
          return { success: false, error: result.error };
        }
        return {
          success: true,
          data: def.mapResult ? def.mapResult(result.data, input) : result.data,
        };
      } catch (e) {
        if (e instanceof RelayError) {
          return { success: false, error: e.message, code: e.code };
        }
        return { success: false, error: "Failed to relay command" };
      }
    },
  });
}
