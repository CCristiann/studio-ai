import {
  SignJWT,
  jwtVerify,
  importPKCS8,
  importSPKI,
  decodeProtectedHeader,
  type CryptoKey,
} from "jose";
import { createSupabaseServerClient } from "./supabase";
import { recordAuthEvent } from "./auth-events";

const ISSUER = "studio-ai";
const AUDIENCE = "studio-ai-plugin";
const TOKEN_TTL_HOURS = 24;
const SIGN_ALG = "RS256";
const SIGN_KID = "v1";

let _privateKey: CryptoKey | null = null;
let _publicKey: CryptoKey | null = null;

function decodePem(value: string): string {
  // Hosts that don't accept multi-line env values (Vercel/Railway when set
  // through the CLI) round-trip newlines as the literal two-character "\n".
  return value.includes("\\n") ? value.replace(/\\n/g, "\n") : value;
}

async function getPrivateKey(): Promise<CryptoKey> {
  if (_privateKey) return _privateKey;
  const pem = process.env.PLUGIN_JWT_PRIVATE_KEY;
  if (!pem) throw new Error("Missing PLUGIN_JWT_PRIVATE_KEY");
  _privateKey = await importPKCS8(decodePem(pem), SIGN_ALG);
  return _privateKey;
}

async function getPublicKey(): Promise<CryptoKey> {
  if (_publicKey) return _publicKey;
  const pem = process.env.PLUGIN_JWT_PUBLIC_KEY;
  if (!pem) throw new Error("Missing PLUGIN_JWT_PUBLIC_KEY");
  _publicKey = await importSPKI(decodePem(pem), SIGN_ALG);
  return _publicKey;
}

function getLegacyHs256Secret(): Uint8Array | null {
  const secret = process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET;
  return secret ? new TextEncoder().encode(secret) : null;
}

export async function signPluginToken(userId: string): Promise<string> {
  const jti = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + TOKEN_TTL_HOURS * 60 * 60 * 1000);

  const supabase = createSupabaseServerClient();
  const { error } = await supabase.from("plugin_tokens").insert({
    jti,
    user_id: userId,
    expires_at: expiresAt.toISOString(),
  });
  if (error) {
    throw new Error(`Failed to store plugin token: ${error.message}`);
  }

  // Fire-and-forget audit event. recordAuthEvent never throws.
  await recordAuthEvent({
    type: "plugin_token_issued",
    userId,
    jti,
    success: true,
  });

  return new SignJWT({ userId, jti })
    .setProtectedHeader({ alg: SIGN_ALG, kid: SIGN_KID })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setIssuedAt()
    .setExpirationTime(`${TOKEN_TTL_HOURS}h`)
    .sign(await getPrivateKey());
}

export async function verifyPluginToken(
  token: string
): Promise<{ userId: string } | null> {
  try {
    const header = decodeProtectedHeader(token);
    let key: CryptoKey | Uint8Array;
    if (header.alg === "RS256") {
      key = await getPublicKey();
    } else if (header.alg === "HS256") {
      // Legacy tokens from before the RS256 cutover. Drop this branch once
      // all HS256 tokens have expired (≤ TOKEN_TTL_HOURS after cutover).
      const secret = getLegacyHs256Secret();
      if (!secret) return null;
      key = secret;
    } else {
      return null;
    }

    const { payload } = await jwtVerify(token, key, {
      issuer: ISSUER,
      audience: AUDIENCE,
    });
    if (typeof payload.userId !== "string" || typeof payload.jti !== "string") {
      return null;
    }

    const supabase = createSupabaseServerClient();
    const { data } = await supabase
      .from("plugin_tokens")
      .select("revoked")
      .eq("jti", payload.jti)
      .single();

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

  await recordAuthEvent({
    type: "plugin_token_revoked",
    userId,
    success: true,
    reason: "sign_out",
  });
}
