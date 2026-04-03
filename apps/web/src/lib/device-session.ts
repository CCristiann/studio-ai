import { createSupabaseServerClient } from "./supabase";
import { randomUUID, randomBytes, createHash } from "crypto";

const DEVICE_SESSION_TTL = 5 * 60 * 1000; // 5 minutes

export function generateDeviceCode(): string {
  return randomBytes(32).toString("base64url");
}

export function hashDeviceCode(code: string): string {
  return createHash("sha256").update(code).digest("hex");
}

export async function createDeviceSession() {
  const supabase = createSupabaseServerClient();
  const sessionId = randomUUID();
  const deviceCode = generateDeviceCode();
  const deviceCodeHash = hashDeviceCode(deviceCode);
  const expiresAt = new Date(Date.now() + DEVICE_SESSION_TTL).toISOString();

  const { error } = await supabase.from("device_sessions").insert({
    session_id: sessionId,
    device_code_hash: deviceCodeHash,
    status: "pending",
    expires_at: expiresAt,
  });

  if (error) throw new Error(`Failed to create device session: ${error.message}`);

  return { sessionId, deviceCode, expiresIn: 300, interval: 2 };
}

export async function findDeviceSession(sessionId: string) {
  const supabase = createSupabaseServerClient();

  const { data, error } = await supabase
    .from("device_sessions")
    .select("*")
    .eq("session_id", sessionId)
    .gt("expires_at", new Date().toISOString())
    .single();

  if (error || !data) return null;
  return data;
}

export async function approveDeviceSession(sessionId: string, userId: string) {
  const supabase = createSupabaseServerClient();

  const { error } = await supabase
    .from("device_sessions")
    .update({ user_id: userId, status: "approved" })
    .eq("session_id", sessionId)
    .eq("status", "pending")
    .gt("expires_at", new Date().toISOString());

  if (error) throw new Error(`Failed to approve device session: ${error.message}`);
}

export async function deleteDeviceSession(sessionId: string) {
  const supabase = createSupabaseServerClient();

  await supabase
    .from("device_sessions")
    .delete()
    .eq("session_id", sessionId);
}
