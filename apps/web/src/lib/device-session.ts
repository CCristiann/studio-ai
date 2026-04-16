import { createSupabaseServerClient } from "./supabase";
import { recordAuthEvent } from "./auth-events";
import { randomUUID, randomBytes, createHash } from "crypto";

const DEVICE_SESSION_TTL = 5 * 60 * 1000; // 5 minutes

export function generateDeviceCode(): string {
  return randomBytes(32).toString("base64url");
}

export function hashDeviceCode(code: string): string {
  return createHash("sha256").update(code).digest("hex");
}

const USER_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // No 0/O/1/I to avoid confusion

export function generateUserCode(): string {
  const bytes = randomBytes(6);
  let code = "";
  for (let i = 0; i < 6; i++) {
    code += USER_CODE_CHARS[bytes[i] % USER_CODE_CHARS.length];
  }
  return code;
}

export function formatUserCode(code: string): string {
  return `${code.slice(0, 3)}-${code.slice(3)}`;
}

export function normalizeUserCode(input: string): string {
  return input.replace(/[-\s]/g, "").toUpperCase();
}

export async function createDeviceSession() {
  const supabase = createSupabaseServerClient();
  const sessionId = randomUUID();
  const deviceCode = generateDeviceCode();
  const deviceCodeHash = hashDeviceCode(deviceCode);
  const userCode = generateUserCode();
  const userCodeHash = hashDeviceCode(userCode); // reuse same SHA-256 hasher
  const expiresAt = new Date(Date.now() + DEVICE_SESSION_TTL).toISOString();

  const { error } = await supabase.from("device_sessions").insert({
    session_id: sessionId,
    device_code_hash: deviceCodeHash,
    user_code_hash: userCodeHash,
    status: "pending",
    expires_at: expiresAt,
  });

  if (error) throw new Error(`Failed to create device session: ${error.message}`);

  return { sessionId, deviceCode, userCode: formatUserCode(userCode), expiresIn: 300, interval: 2 };
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

export async function findDeviceSessionByUserCode(userCode: string) {
  const supabase = createSupabaseServerClient();
  const normalized = normalizeUserCode(userCode);
  const codeHash = hashDeviceCode(normalized);

  const { data, error } = await supabase
    .from("device_sessions")
    .select("*")
    .eq("user_code_hash", codeHash)
    .eq("status", "pending")
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

  await recordAuthEvent({
    type: "device_code_approved",
    userId,
    sessionId,
    success: true,
  });
}

export async function deleteDeviceSession(sessionId: string) {
  const supabase = createSupabaseServerClient();

  await supabase
    .from("device_sessions")
    .delete()
    .eq("session_id", sessionId);
}
