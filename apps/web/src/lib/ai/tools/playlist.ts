// apps/web/src/lib/ai/tools/playlist.ts
import { z } from "zod";
import { relayTool } from "./_shared";

const PL_INDEX = z.number().int().min(1).max(500).describe("Playlist track index (1-indexed; FL 20+ caps at 500)");
const COLOR_RGB = z.number().int().min(0).max(0xFFFFFF);

export function playlistTools(userId: string) {
  return {
    rename_playlist_track: relayTool(userId, {
      description: "Rename a single playlist track (1-indexed). For many at once, prefer apply_organization_plan.",
      inputSchema: z.object({
        index: PL_INDEX,
        name: z.string().min(1).max(128),
      }),
      toRelay: ({ index, name }) => ({ action: "rename_playlist_track", params: { index, name } }),
    }),

    set_playlist_track_color: relayTool(userId, {
      description: "Set the color of a playlist track (1-indexed, 24-bit RGB).",
      inputSchema: z.object({ index: PL_INDEX, color: COLOR_RGB }),
      toRelay: ({ index, color }) => ({ action: "set_playlist_track_color", params: { index, color } }),
    }),

    find_playlist_track_by_name: relayTool(userId, {
      description: "Find playlist tracks by name (fuzzy substring match, 1-indexed). Returns up to `limit` matches sorted by score.",
      inputSchema: z.object({
        query: z.string().min(1).max(128),
        limit: z.number().int().min(1).max(20).optional().default(5),
      }),
      toRelay: ({ query, limit }) => ({ action: "find_playlist_track_by_name", params: { query, limit } }),
    }),
  };
}
