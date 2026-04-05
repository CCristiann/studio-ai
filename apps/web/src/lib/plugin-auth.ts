import { SignJWT, jwtVerify } from "jose";
import { createSupabaseServerClient } from "./supabase";

const ISSUER = "studio-ai";
const AUDIENCE = "studio-ai-plugin";
const TOKEN_TTL_HOURS = 24;

function getSecret() {
  const secret = process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET;
  if (!secret) throw new Error("Missing NEXTAUTH_SECRET");
  return new TextEncoder().encode(secret);
}

export async function signPluginToken(userId: string): Promise<string> {
  const jti = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + TOKEN_TTL_HOURS * 60 * 60 * 1000);

  // Store token record for revocation support
  const supabase = createSupabaseServerClient();
  const { error } = await supabase.from("plugin_tokens").insert({
    jti,
    user_id: userId,
    expires_at: expiresAt.toISOString(),
  });
  if (error) {
    throw new Error(`Failed to store plugin token: ${error.message}`);
  }

  return new SignJWT({ userId, jti })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setIssuedAt()
    .setExpirationTime(`${TOKEN_TTL_HOURS}h`)
    .sign(getSecret());
}

export async function verifyPluginToken(
  token: string
): Promise<{ userId: string } | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret(), {
      issuer: ISSUER,
      audience: AUDIENCE,
    });
    if (typeof payload.userId !== "string" || typeof payload.jti !== "string") {
      return null;
    }

    // Check if token has been revoked
    const supabase = createSupabaseServerClient();
    const { data } = await supabase
      .from("plugin_tokens")
      .select("revoked")
      .eq("jti", payload.jti)
      .single();

    // If no record found or revoked, reject
    if (!data || data.revoked) {
      return null;
    }

    return { userId: payload.userId };
  } catch {
    return null;
  }
}

/** Revoke all active plugin tokens for a user (called on sign-out). */
export async function revokePluginTokensForUser(userId: string): Promise<void> {
  const supabase = createSupabaseServerClient();
  await supabase
    .from("plugin_tokens")
    .update({ revoked: true })
    .eq("user_id", userId)
    .eq("revoked", false);
}
