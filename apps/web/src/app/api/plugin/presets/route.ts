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
  const { data, error } = await supabase
    .from("presets")
    .select("id, name, description, prompt, created_at, updated_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ presets: data });
}

export async function POST(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { name, description, prompt } = body;

  if (!name || !prompt) {
    return NextResponse.json({ error: "name and prompt are required" }, { status: 400 });
  }

  const supabase = createSupabaseServerClient();
  const { data, error } = await supabase
    .from("presets")
    .insert({ user_id: userId, name, description: description ?? null, prompt })
    .select("id, name, description, prompt, created_at, updated_at")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ preset: data }, { status: 201 });
}
