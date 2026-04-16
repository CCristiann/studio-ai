import { createDeviceSession } from "@/lib/device-session";
import { rateLimit, getClientIp } from "@/lib/rate-limit";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // Rate limit: max 5 device sessions per IP per minute
  const ip = getClientIp(req);
  const { success } = await rateLimit(`device-create:${ip}`, {
    limit: 5,
    windowMs: 60_000,
  });
  if (!success) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429 }
    );
  }

  // CSRF: verify request comes from our origin
  const origin = req.headers.get("origin");
  const referer = req.headers.get("referer");
  const host = req.headers.get("host");

  if (origin && host && !origin.includes(host)) {
    return NextResponse.json(
      { error: "Invalid origin" },
      { status: 403 }
    );
  }
  if (!origin && !referer) {
    return NextResponse.json(
      { error: "Missing origin" },
      { status: 403 }
    );
  }

  try {
    const session = await createDeviceSession();

    return NextResponse.json({
      session_id: session.sessionId,
      device_code: session.deviceCode,
      user_code: session.userCode,
      expires_in: session.expiresIn,
      interval: session.interval,
    });
  } catch (error) {
    console.error("Device session creation failed:", error);
    return NextResponse.json(
      { error: "Failed to create device session" },
      { status: 500 }
    );
  }
}
