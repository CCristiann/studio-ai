import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { rateLimit } from "@/lib/rate-limit";
import { runAnalysis } from "@/lib/ai/organize/analysis-agent";
import { runOrganization, runScaffold, adjustPlan } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { executePlan, validateStateBeforeExecution } from "@/lib/ai/organize/execute-plan";
import type { AIPlan, EnhancedProjectState } from "@studio-ai/types";

async function getUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  const session = await auth();
  return session?.userId ?? null;
}

/**
 * POST /api/ai/organize
 *
 * Body variants:
 *   { action: "analyze" }                           → Run analysis + organization, return preview
 *   { action: "scaffold", genre: string }           → Generate new project template, return preview
 *   { action: "adjust", plan: AIPlan, feedback: string, projectState } → Adjust plan
 *   { action: "execute", plan: AIPlan, channelCount: number, projectState } → Execute plan
 */
export async function POST(req: Request) {
  const userId = await getUserId(req);
  if (!userId) {
    return new Response("Unauthorized", { status: 401 });
  }

  const { success } = rateLimit(`organize:${userId}`, {
    limit: 10,
    windowMs: 60_000,
  });
  if (!success) {
    return new Response("Rate limit exceeded", { status: 429 });
  }

  try {
    const body = await req.json();
    const { action } = body;

    if (action === "analyze") {
      const { projectMap, projectState } = await runAnalysis(userId);
      const aiPlan = await runOrganization(projectMap, projectState);
      const fullPlan = expandPlan(aiPlan, projectState);

      return NextResponse.json({ success: true, aiPlan, plan: fullPlan, projectState });
    }

    if (action === "scaffold") {
      const { genre } = body as { genre: string };
      if (!genre) {
        return NextResponse.json({ error: "genre is required" }, { status: 400 });
      }
      const aiPlan = await runScaffold(genre);

      const emptyState: EnhancedProjectState = {
        bpm: 140,
        project_name: "New Project",
        channels: aiPlan.channelAssignments.map((a, i) => ({
          index: i,
          name: `Channel ${i + 1}`,
          plugin: "Sampler",
          color: 0,
          volume: 0.8,
          pan: 0,
          enabled: true,
          insert: i + 1,
        })),
        mixer_tracks: aiPlan.channelAssignments.map((a, i) => ({
          index: i + 1,
          name: `Insert ${i + 1}`,
          color: 0,
          volume: 0.8,
          pan: 0,
          muted: false,
        })),
        playlist_tracks: [],
        patterns: aiPlan.channelAssignments.map((a, i) => ({
          index: i + 1,
          name: `Pattern ${i + 1}`,
          color: 0,
        })),
      };

      const fullPlan = expandPlan(aiPlan, emptyState);
      return NextResponse.json({ success: true, aiPlan, plan: fullPlan, projectState: emptyState });
    }

    if (action === "adjust") {
      const { plan: currentPlan, feedback, projectState } = body as {
        plan: AIPlan;
        feedback: string;
        projectState: EnhancedProjectState;
      };
      if (!currentPlan || !feedback) {
        return NextResponse.json({ error: "plan and feedback are required" }, { status: 400 });
      }
      const adjustedAiPlan = await adjustPlan(currentPlan, feedback);
      const fullPlan = expandPlan(adjustedAiPlan, projectState);

      return NextResponse.json({ success: true, aiPlan: adjustedAiPlan, plan: fullPlan });
    }

    if (action === "execute") {
      const { plan: aiPlan, channelCount, projectState } = body as {
        plan: AIPlan;
        channelCount: number;
        projectState: EnhancedProjectState;
      };
      if (!aiPlan) {
        return NextResponse.json({ error: "plan is required" }, { status: 400 });
      }

      const validation = await validateStateBeforeExecution(userId, channelCount);
      if (!validation.valid) {
        return NextResponse.json({
          success: false,
          error: "stale_state",
          message: `Project changed since analysis. Expected ${channelCount} channels, found ${validation.currentChannelCount}. Please re-analyze.`,
        }, { status: 409 });
      }

      const fullPlan = expandPlan(aiPlan, projectState);
      const result = await executePlan(userId, fullPlan);

      return NextResponse.json({ success: result.failures.length === 0, result });
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
