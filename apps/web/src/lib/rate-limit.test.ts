import { describe, it, expect, vi, beforeEach } from "vitest";

// --- Mock the Redis module ---------------------------------------------------
// vi.mock is hoisted above imports, so we use vi.hoisted() to share refs.
const { execMock, incrMock, expireMock } = vi.hoisted(() => ({
  execMock: vi.fn(),
  incrMock: vi.fn(),
  expireMock: vi.fn(),
}));

vi.mock("./redis", () => {
  const multi = {
    incr: (...args: unknown[]) => {
      incrMock(...args);
      return multi;
    },
    expire: (...args: unknown[]) => {
      expireMock(...args);
      return multi;
    },
    exec: execMock,
  };
  return {
    getRedisClient: () => ({ multi: () => multi }),
  };
});

// Import after mock setup so the rate limiter picks up the fake client.
import { rateLimit } from "./rate-limit";

beforeEach(() => {
  execMock.mockReset();
  incrMock.mockReset();
  expireMock.mockReset();
  // Default: simulate first-INCR success with TTL applied.
  execMock.mockResolvedValue([
    [null, 1], // INCR -> 1
    [null, 1], // EXPIRE NX -> 1 (applied)
  ]);
});

describe("rateLimit (Redis-backed, fixed window)", () => {
  it("first request in a window: permits and counts 1 toward the limit", async () => {
    execMock.mockResolvedValueOnce([[null, 1], [null, 1]]);

    const result = await rateLimit("device-create:1.2.3.4", {
      limit: 5,
      windowMs: 60_000,
    });

    expect(result).toEqual({ success: true, remaining: 4 });
    expect(incrMock).toHaveBeenCalledWith(
      "ratelimit:device-create:1.2.3.4"
    );
    expect(expireMock).toHaveBeenCalledWith(
      "ratelimit:device-create:1.2.3.4",
      60,
      "NX"
    );
  });

  it("within the limit: permits with correct remaining count", async () => {
    execMock.mockResolvedValueOnce([[null, 3], [null, 0]]);

    const result = await rateLimit("device-token:1.2.3.4", {
      limit: 30,
      windowMs: 60_000,
    });

    expect(result).toEqual({ success: true, remaining: 27 });
  });

  it("at the limit boundary: permits with remaining=0", async () => {
    execMock.mockResolvedValueOnce([[null, 5], [null, 0]]);

    const result = await rateLimit("device-code:abc", {
      limit: 5,
      windowMs: 300_000,
    });

    expect(result).toEqual({ success: true, remaining: 0 });
  });

  it("over the limit: denies with remaining=0", async () => {
    execMock.mockResolvedValueOnce([[null, 6], [null, 0]]);

    const result = await rateLimit("device-code:abc", {
      limit: 5,
      windowMs: 300_000,
    });

    expect(result).toEqual({ success: false, remaining: 0 });
  });

  it("fractional windowMs rounds up to at least 1 second of TTL", async () => {
    execMock.mockResolvedValueOnce([[null, 1], [null, 1]]);

    await rateLimit("short", { limit: 10, windowMs: 500 });

    expect(expireMock).toHaveBeenCalledWith(
      "ratelimit:short",
      1,
      "NX"
    );
  });

  it("Redis throws: fails open (permits) and does not propagate", async () => {
    execMock.mockRejectedValueOnce(new Error("ECONNREFUSED"));

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = await rateLimit("ai:user-123", {
      limit: 20,
      windowMs: 60_000,
    });

    expect(result).toEqual({ success: true, remaining: 19 });
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("INCR reply error inside MULTI: fails open and logs", async () => {
    execMock.mockResolvedValueOnce([
      [new Error("WRONGTYPE"), null],
      [null, 0],
    ]);

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = await rateLimit("organize:user-123", {
      limit: 10,
      windowMs: 60_000,
    });

    expect(result).toEqual({ success: true, remaining: 9 });
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("empty MULTI result: fails open", async () => {
    execMock.mockResolvedValueOnce(null);

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = await rateLimit("key", { limit: 10, windowMs: 60_000 });

    expect(result).toEqual({ success: true, remaining: 9 });
    warnSpy.mockRestore();
  });

  it("key prefix isolates rate-limit namespace from other Redis data", async () => {
    execMock.mockResolvedValueOnce([[null, 1], [null, 1]]);

    await rateLimit("foo", { limit: 1, windowMs: 1000 });

    expect(incrMock).toHaveBeenCalledWith("ratelimit:foo");
  });
});
