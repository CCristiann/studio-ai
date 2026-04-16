/**
 * Audit trail for authentication lifecycle events — audit finding M8.
 *
 * Writes one row per event to the `auth_events` table (see migration 012).
 * This is a **best-effort, fail-open** logger: insertion errors are surfaced
 * to the server console but never thrown, because an audit-pipe outage must
 * not break sign-in, token issuance, or device-code approval.
 *
 * Event shape rationale:
 * - `userId` is optional because login-failure events record attempts by users
 *   we may not know yet, and device-code events happen before approval.
 * - `sessionId` / `jti` narrow the event to the specific auth object so the
 *   ops dashboard can say "these five failed logins share a session".
 * - `ip` + `userAgent` are recorded *when available* — the call sites pull
 *   them from request headers. We truncate `userAgent` to 512 chars as a
 *   cheap defense against malicious clients stuffing the field.
 * - `metadata` is the escape hatch for per-event-type context we haven't
 *   promoted to a column yet. Keep it small; don't dump full request bodies.
 *
 * NEVER put secrets (tokens, device codes, passwords) into any field, including
 * metadata. This table is readable by anyone with service-role access and is
 * retained for 90 days — treat it as medium-sensitive PII.
 */

import { createSupabaseServerClient } from "./supabase";

export type AuthEventType =
  | "plugin_token_issued"
  | "plugin_token_revoked"
  | "device_code_approved"
  | "login_succeeded"
  | "login_failed";

export interface AuthEventInput {
  type: AuthEventType;
  userId?: string | null;
  sessionId?: string | null;
  jti?: string | null;
  ip?: string | null;
  userAgent?: string | null;
  success: boolean;
  reason?: string | null;
  metadata?: Record<string, unknown>;
}

const USER_AGENT_MAX_LEN = 512;

export async function recordAuthEvent(input: AuthEventInput): Promise<void> {
  const userAgent = input.userAgent
    ? input.userAgent.slice(0, USER_AGENT_MAX_LEN)
    : null;

  try {
    const supabase = createSupabaseServerClient();
    const { error } = await supabase.from("auth_events").insert({
      event_type: input.type,
      user_id: input.userId ?? null,
      session_id: input.sessionId ?? null,
      jti: input.jti ?? null,
      ip: input.ip ?? null,
      user_agent: userAgent,
      success: input.success,
      reason: input.reason ?? null,
      metadata: input.metadata ?? {},
    });
    if (error) {
      console.warn("[auth-events] insert failed", {
        type: input.type,
        error: error.message,
      });
    }
  } catch (err) {
    // Guard against createSupabaseServerClient() throwing (missing env vars
    // at build time) or network-level failures. An audit-pipe outage must
    // never block auth.
    console.warn("[auth-events] unexpected error, swallowing", {
      type: input.type,
      err: err instanceof Error ? err.message : String(err),
    });
  }
}

/**
 * Extract a best-effort client IP from a standard Request. Handles the
 * common forwarded-header variants used by Vercel / Cloudflare / nginx.
 * Returns `null` if nothing usable is present.
 */
export function getRequestIp(req: Request): string | null {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) {
    // "client, proxy1, proxy2" — the first entry is the original client.
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return req.headers.get("x-real-ip") ?? null;
}
