import { getRedisClient } from "./redis";

const PREFIX = "ratelimit:";

/**
 * Atomic fixed-window rate limiter backed by Redis.
 *
 * Closes audit finding H2: previously this module kept an in-memory `Map`
 * that reset on every cold start, effectively disabling rate limiting in
 * serverless deploys. The Redis-backed counter survives cold starts and
 * coordinates across lambda instances.
 *
 * Implementation: `INCR key` + `EXPIRE key windowSec NX` inside a MULTI.
 * The `NX` flag (Redis ≥ 7.0) ensures the TTL is set exactly once per
 * window — subsequent increments inside the same window don't reset it,
 * so the window is truly fixed rather than sliding on each request.
 *
 * All major managed Redis providers (Upstash, Railway, Supabase, DigitalOcean)
 * run Redis 7.0+ by default in 2026. If targeting an older Redis, EXPIRE NX
 * will fail and the counter will grow without bound — that's a deliberately
 * loud failure mode; better than silently rolling forever.
 *
 * Failure policy: any Redis error → **fail open** (permit the request) +
 * `console.warn`. Locking out all users during a Redis outage is worse UX
 * than the marginal bypass risk during the outage window. The logs make
 * silent bypass observable; monitor for spikes.
 */
export async function rateLimit(
  key: string,
  { limit, windowMs }: { limit: number; windowMs: number }
): Promise<{ success: boolean; remaining: number }> {
  const fullKey = PREFIX + key;
  // EXPIRE takes whole seconds; round up so sub-second windows still get a TTL.
  const windowSec = Math.max(1, Math.ceil(windowMs / 1000));

  try {
    const redis = getRedisClient();
    const results = await redis
      .multi()
      .incr(fullKey)
      .expire(fullKey, windowSec, "NX")
      .exec();

    if (!results || results.length === 0) {
      console.warn("[rate-limit] empty MULTI result, failing open", { key });
      return { success: true, remaining: limit - 1 };
    }

    const [incrErr, countRaw] = results[0] as [Error | null, unknown];
    if (incrErr) {
      console.warn("[rate-limit] INCR error, failing open", {
        key,
        error: incrErr.message,
      });
      return { success: true, remaining: limit - 1 };
    }

    const count =
      typeof countRaw === "number" ? countRaw : Number(countRaw ?? 0);
    const remaining = Math.max(0, limit - count);
    return { success: count <= limit, remaining };
  } catch (err) {
    console.warn("[rate-limit] Redis error, failing open", {
      key,
      error: err instanceof Error ? err.message : String(err),
    });
    return { success: true, remaining: limit - 1 };
  }
}

export function getClientIp(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return "unknown";
}
