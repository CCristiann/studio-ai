import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { rateLimit } from "@/lib/rate-limit";
import { runAnalysis } from "@/lib/ai/organize/analysis-agent";
import { runOrganization, runScaffold, adjustPlan } from "@/lib/ai/organize/organization-agent";
import { expandPlan } from "@/lib/ai/organize/expand-plan";
import { executePlan, validateStateBeforeExecution } from "@/lib/ai/organize/execute-plan";
import type { AIPlan, EnhancedProjectState } from "@repo/types";

async function getUserId(req: Request): Promise<string | null> {
  // 1. Try Bearer token (plugin WebView)
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  // 2. Fall back to session cookie (browser dashboard)
  const session = await auth();
  return session?.userId ?? null;
}

export async function POST(req: Request) {
  const userId = await getUserId(req);
  if (!userId) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Rate limit: max 10 organize requests per user per minute
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
      // Stage 1: analysis
      const analysisResult = await runAnalysis(userId);
      // Stage 2: organization — produces a preview plan
      const { aiPlan, projectState } = await runOrganization(userId, analysisResult);
      // Expand into human-readable plan
      const plan = expandPlan(aiPlan);

      return NextResponse.json({ success: true, aiPlan, plan, projectState });
    }

    if (action === "scaffold") {
      const { genre } = body as { genre: string };
      // Generate a new project template for the given genre
      const aiPlan = await runScaffold(genre);

      // Synthesize an empty project state from the scaffold plan
      const emptyState: EnhancedProjectState = {
        bpm: 140,
        project_name: "New Project",
        channels: aiPlan.channelAssignments.map((a: unknown, i: number) => ({
          index: i,
          name: `Channel ${i + 1}`,
          plugin: "Sampler",
          color: 0,
          volume: 0.8,
          pan: 0,
          enabled: true,
          insert: i + 1,
        })),
        mixer_tracks: aiPlan.channelAssignments.map((a: unknown, i: number) => ({
          index: i + 1,
          name: `Insert ${i + 1}`,
          color: 0,
          volume: 0.8,
          pan: 0,
          muted: false,
        })),
        playlist_tracks: [],
        patterns: aiPlan.channelAssignments.map((a: unknown, i: number) => ({
          index: i + 1,
          name: `Pattern ${i + 1}`,
          color: 0,
        })),
      };

      const plan = expandPlan(aiPlan);

      return NextResponse.json({ success: true, aiPlan, plan, projectState: emptyState });
    }

    if (action === "adjust") {
      const { plan: aiPlan, feedback, projectState } = body as {
        plan: AIPlan;
        feedback: string;
        projectState: EnhancedProjectState;
      };

      const adjustedPlan = await adjustPlan(aiPlan, feedback, projectState);
      const plan = expandPlan(adjustedPlan);

      return NextResponse.json({ success: true, aiPlan: adjustedPlan, plan });
    }

    if (action === "execute") {
      const { plan: aiPlan, channelCount, projectState } = body as {
        plan: AIPlan;
        channelCount: number;
        projectState: EnhancedProjectState;
      };

      // Validate the live state hasn't changed since the plan was previewed
      const isValid = await validateStateBeforeExecution(userId, projectState, channelCount);
      if (!isValid) {
        return NextResponse.json(
          { success: false, error: "Project state has changed since plan was generated. Please re-analyze." },
          { status: 409 }
        );
      }

      const result = await executePlan(userId, aiPlan);

      return NextResponse.json({ success: true, result });
    }

    return NextResponse.json({ success: false, error: `Unknown action: ${action}` }, { status: 400 });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Internal server error";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
