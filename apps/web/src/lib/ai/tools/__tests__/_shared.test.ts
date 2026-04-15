import { describe, it, expect, vi, beforeEach } from "vitest";
import { z } from "zod";

// Mock @/lib/relay BEFORE importing _shared
vi.mock("@/lib/relay", () => {
  class RelayError extends Error {
    code: string;
    statusCode: number;
    constructor(code: string, message: string, statusCode: number) {
      super(message);
      this.name = "RelayError";
      this.code = code;
      this.statusCode = statusCode;
    }
  }
  return {
    relay: vi.fn(),
    RelayError,
  };
});

import { relay, RelayError } from "@/lib/relay";
import { relayTool } from "../_shared";

const mockedRelay = vi.mocked(relay);

describe("relayTool", () => {
  beforeEach(() => {
    mockedRelay.mockReset();
  });

  it("forwards input through toRelay() and returns success on relay success", async () => {
    mockedRelay.mockResolvedValue({
      id: "x",
      success: true,
      data: { bpm: 128 },
    });
    const t = relayTool("user-1", {
      description: "set bpm",
      inputSchema: z.object({ bpm: z.number() }),
      toRelay: ({ bpm }) => ({ action: "set_bpm", params: { bpm } }),
    });
    const result = await t.execute!({ bpm: 128 }, {} as any);
    expect(mockedRelay).toHaveBeenCalledWith("user-1", "set_bpm", { bpm: 128 });
    expect(result).toEqual({ success: true, data: { bpm: 128 } });
  });

  it("applies mapResult when provided", async () => {
    mockedRelay.mockResolvedValue({ id: "x", success: true, data: { bpm: 128 } });
    const t = relayTool("u", {
      description: "set bpm with bpm-only result",
      inputSchema: z.object({ bpm: z.number() }),
      toRelay: ({ bpm }) => ({ action: "set_bpm", params: { bpm } }),
      mapResult: (data, input) => ({ before: input.bpm, after: (data as any).bpm }),
    });
    const result = await t.execute!({ bpm: 128 }, {} as any);
    expect(result).toEqual({
      success: true,
      data: { before: 128, after: 128 },
    });
  });

  it("returns success:false with the relay's error on relay-level failure", async () => {
    mockedRelay.mockResolvedValue({
      id: "x",
      success: false,
      data: null,
      error: "DAW says no",
    });
    const t = relayTool("u", {
      description: "x",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "noop", params: {} }),
    });
    const result = await t.execute!({}, {} as any);
    expect(result).toEqual({ success: false, error: "DAW says no" });
  });

  it("maps RelayError to {success:false, error, code}", async () => {
    mockedRelay.mockRejectedValue(new RelayError("DAW_TIMEOUT", "timed out", 504));
    const t = relayTool("u", {
      description: "x",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "noop", params: {} }),
    });
    const result = await t.execute!({}, {} as any);
    expect(result).toEqual({ success: false, error: "timed out", code: "DAW_TIMEOUT" });
  });

  it("maps unknown errors to a generic message", async () => {
    mockedRelay.mockRejectedValue(new Error("network blew up"));
    const t = relayTool("u", {
      description: "x",
      inputSchema: z.object({}),
      toRelay: () => ({ action: "noop", params: {} }),
    });
    const result = await t.execute!({}, {} as any);
    expect(result).toEqual({ success: false, error: "Failed to relay command" });
  });
});
