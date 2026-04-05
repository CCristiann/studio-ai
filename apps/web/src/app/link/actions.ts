"use server";

import { auth } from "@/lib/auth";
import { findDeviceSessionByUserCode, approveDeviceSession } from "@/lib/device-session";
import { rateLimit } from "@/lib/rate-limit";

export async function verifyUserCode(
  _prevState: { error?: string; success?: boolean },
  formData: FormData
): Promise<{ error?: string; success?: boolean }> {
  const session = await auth();
  if (!session?.userId) {
    return { error: "Not authenticated" };
  }

  // Rate limit: max 10 code attempts per user per minute
  const { success: allowed } = rateLimit(`link-code:${session.userId}`, {
    limit: 10,
    windowMs: 60_000,
  });
  if (!allowed) {
    return { error: "Too many attempts. Please wait a moment and try again." };
  }

  const code = formData.get("code");
  if (typeof code !== "string" || code.trim().length === 0) {
    return { error: "Please enter a code" };
  }

  const deviceSession = await findDeviceSessionByUserCode(code);
  if (!deviceSession) {
    return { error: "Invalid or expired code. Check the code in your plugin and try again." };
  }

  try {
    await approveDeviceSession(deviceSession.session_id, session.userId);
  } catch {
    return { error: "Failed to authorize. The code may have expired." };
  }

  return { success: true };
}
