import { createDeviceSession } from "@/lib/device-session";
import { NextResponse } from "next/server";

export async function POST() {
  try {
    const session = await createDeviceSession();

    return NextResponse.json({
      session_id: session.sessionId,
      device_code: session.deviceCode,
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
