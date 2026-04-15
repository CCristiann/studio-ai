// apps/web/src/lib/ai/tools/index.ts
import { transportTools } from "./transport";
import { channelTools }  from "./channels";
import { mixerTools }    from "./mixer";
import { playlistTools } from "./playlist";
import { patternTools }  from "./patterns";
import { projectTools }  from "./project";
import { organizeTools } from "./organize";

export function composeTools(userId: string) {
  return {
    ...transportTools(userId),
    ...channelTools(userId),
    ...mixerTools(userId),
    ...playlistTools(userId),
    ...patternTools(userId),
    ...projectTools(userId),
    ...organizeTools(userId),
  };
}
