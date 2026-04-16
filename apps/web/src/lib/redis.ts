import Redis from "ioredis";

/**
 * Singleton ioredis client for the Next.js app.
 *
 * Stored on `globalThis` so HMR in `next dev` doesn't leak a new connection
 * every time this module re-evaluates. In production (Vercel lambda) each
 * cold start creates one connection that the instance reuses across requests.
 *
 * The client is **lazily connected**: the socket is not opened until the
 * first command. This keeps `next build` (and any route analysis that
 * merely imports this module) from failing on hosts without Redis.
 *
 * REDIS_URL is required at first use, not at import time. Callers that can
 * tolerate Redis being unavailable should wrap their calls in try/catch —
 * see `rate-limit.ts` for the canonical fail-open pattern.
 */

const globalForRedis = globalThis as unknown as {
  _studioAiRedis?: Redis;
};

function createClient(): Redis {
  const url = process.env.REDIS_URL;
  if (!url) {
    throw new Error(
      "[redis] REDIS_URL is not set. Set it in .env.local (dev) or the host's env (prod)."
    );
  }
  return new Redis(url, {
    lazyConnect: true,
    // 3 retries per command keeps latency bounded; the client keeps
    // reconnecting in the background between retries.
    maxRetriesPerRequest: 3,
    enableOfflineQueue: true,
  });
}

export function getRedisClient(): Redis {
  if (!globalForRedis._studioAiRedis) {
    globalForRedis._studioAiRedis = createClient();
  }
  return globalForRedis._studioAiRedis;
}
