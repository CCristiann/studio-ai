import { NextResponse } from "next/server";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { createSupabaseServerClient } from "@/lib/supabase";

async function getPluginUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return null;
  const result = await verifyPluginToken(authHeader.slice(7));
  return result?.userId ?? null;
}

export async function GET(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const supabase = createSupabaseServerClient();
  const { data } = await supabase
    .from("user_preferences")
    .select("onboarding_completed")
    .eq("user_id", userId)
    .single();

  return NextResponse.json({
    preferences: data ?? { onboarding_completed: false },
  });
}

export async function PATCH(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const supabase = createSupabaseServerClient();

  const { data, error } = await supabase
    .from("user_preferences")
    .upsert(
      {
        user_id: userId,
        onboarding_completed: body.onboarding_completed ?? false,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id" }
    )
    .select("onboarding_completed")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ preferences: data });
}
