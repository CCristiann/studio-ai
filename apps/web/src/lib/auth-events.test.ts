import { describe, it, expect, vi, beforeEach } from "vitest";

// Share refs between vi.mock (hoisted) and the test body.
const { fromMock, insertMock } = vi.hoisted(() => ({
  fromMock: vi.fn(),
  insertMock: vi.fn(),
}));

vi.mock("./supabase", () => ({
  createSupabaseServerClient: () => ({
    from: (table: string) => {
      fromMock(table);
      return { insert: insertMock };
    },
  }),
}));

import { recordAuthEvent } from "./auth-events";

beforeEach(() => {
  fromMock.mockReset();
  insertMock.mockReset();
  insertMock.mockResolvedValue({ error: null });
});

describe("recordAuthEvent", () => {
  it("inserts into the auth_events table", async () => {
    await recordAuthEvent({ type: "plugin_token_issued", success: true });
    expect(fromMock).toHaveBeenCalledWith("auth_events");
  });

  it("maps camelCase input to snake_case DB columns", async () => {
    await recordAuthEvent({
      type: "device_code_approved",
      userId: "user-123",
      sessionId: "11111111-2222-3333-4444-555555555555",
      jti: "abc-jti",
      ip: "1.2.3.4",
      userAgent: "TestAgent/1.0",
      success: true,
      reason: "verified",
      metadata: { foo: "bar" },
    });

    expect(insertMock).toHaveBeenCalledWith({
      event_type: "device_code_approved",
      user_id: "user-123",
      session_id: "11111111-2222-3333-4444-555555555555",
      jti: "abc-jti",
      ip: "1.2.3.4",
      user_agent: "TestAgent/1.0",
      success: true,
      reason: "verified",
      metadata: { foo: "bar" },
    });
  });

  it("defaults omitted optional fields to null / empty metadata", async () => {
    await recordAuthEvent({ type: "login_succeeded", success: true });

    expect(insertMock).toHaveBeenCalledWith({
      event_type: "login_succeeded",
      user_id: null,
      session_id: null,
      jti: null,
      ip: null,
      user_agent: null,
      success: true,
      reason: null,
      metadata: {},
    });
  });

  it("records login_failed with reason + no user_id", async () => {
    await recordAuthEvent({
      type: "login_failed",
      success: false,
      reason: "OAuthCallbackError",
    });

    expect(insertMock).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: "login_failed",
        success: false,
        reason: "OAuthCallbackError",
        user_id: null,
      })
    );
  });

  it("truncates overlong user_agent to 512 chars (prevents blob attacks)", async () => {
    const long = "A".repeat(2000);
    await recordAuthEvent({
      type: "login_succeeded",
      userAgent: long,
      success: true,
    });

    const payload = insertMock.mock.calls[0][0] as { user_agent: string };
    expect(payload.user_agent).toHaveLength(512);
  });

  it("fails open when supabase returns an error (logs, does not throw)", async () => {
    insertMock.mockResolvedValueOnce({ error: { message: "oops" } });
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(
      recordAuthEvent({ type: "plugin_token_issued", success: true })
    ).resolves.toBeUndefined();

    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("fails open when supabase client throws (logs, does not throw)", async () => {
    insertMock.mockRejectedValueOnce(new Error("network down"));
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(
      recordAuthEvent({ type: "plugin_token_revoked", success: true })
    ).resolves.toBeUndefined();

    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("accepts every declared event type", async () => {
    const types = [
      "plugin_token_issued",
      "plugin_token_revoked",
      "device_code_approved",
      "login_succeeded",
      "login_failed",
    ] as const;

    for (const type of types) {
      await recordAuthEvent({ type, success: true });
    }
    expect(insertMock).toHaveBeenCalledTimes(types.length);
  });
});
