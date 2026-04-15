import { z } from "zod";
import { relayTool } from "./_shared";

export function projectTools(userId: string) {
  return {
    get_project_state: relayTool(userId, {
      description: "Get the current state of the DAW project including BPM, tracks, and project name.",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "get_state", params: {} }),
    }),
  };
}
