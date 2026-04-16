import { findDeviceSession, deleteDeviceSession, hashDeviceCode } from "@/lib/device-session";
import { signPluginToken } from "@/lib/plugin-auth";
import { rateLimit, getClientIp } from "@/lib/rate-limit";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // Rate limit: max 30 polls per IP per minute (1 every 2s)
  const ip = getClientIp(req);
  const { success } = await rateLimit(`device-token:${ip}`, {
    limit: 30,
    windowMs: 60_000,
  });
  if (!success) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429 }
    );
  }

  let body: { session_id?: string; device_code?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { session_id, device_code } = body;

  if (!session_id || !device_code) {
    return NextResponse.json(
      { error: "Missing session_id or device_code" },
      { status: 400 }
    );
  }

  const session = await findDeviceSession(session_id);

  if (!session) {
    return NextResponse.json({ status: "expired" });
  }

  // Verify device_code matches stored hash
  const codeHash = hashDeviceCode(device_code);
  if (codeHash !== session.device_code_hash) {
    // Rate limit invalid code attempts per session (max 5)
    const { success: codeOk } = await rateLimit(`device-code:${session_id}`, {
      limit: 5,
      windowMs: 300_000,
    });
    if (!codeOk) {
      return NextResponse.json(
        { error: "Too many invalid attempts" },
        { status: 429 }
      );
    }
    return NextResponse.json({ error: "Invalid device code" }, { status: 401 });
  }

  if (session.status === "pending") {
    return NextResponse.json({ status: "pending" });
  }

  if (session.status === "approved" && session.user_id) {
    // Generate JWT and delete the session (one-time use)
    const token = await signPluginToken(session.user_id);
    await deleteDeviceSession(session.session_id);

    return NextResponse.json({ status: "complete", token });
  }

  return NextResponse.json({ status: "expired" });
}
