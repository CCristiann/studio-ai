import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { approveDeviceSession, findDeviceSession } from "@/lib/device-session";

export default async function AuthorizeDevicePage({
  searchParams,
}: {
  searchParams: Promise<{ session_id?: string; context?: string }>;
}) {
  const { session_id, context } = await searchParams;
  const isPlugin = context === "plugin";

  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (!session_id || !uuidRegex.test(session_id)) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-destructive">Invalid session ID.</p>
      </div>
    );
  }

  const userSession = await auth();

  if (!userSession?.userId) {
    const callbackUrl = `/auth/device/authorize?session_id=${session_id}${isPlugin ? "&context=plugin" : ""}`;
    redirect(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`);
  }

  const deviceSession = await findDeviceSession(session_id);

  if (!deviceSession) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center space-y-2">
          <h1 className="text-xl font-semibold">Session Expired</h1>
          <p className="text-muted-foreground">
            This authorization request has expired. Go back to the plugin and try again.
          </p>
        </div>
      </div>
    );
  }

  // Already approved — redirect back to plugin
  if (deviceSession.status === "approved") {
    redirect("/plugin?context=plugin");
  }

  async function approve() {
    "use server";

    const userSession = await auth();
    if (!userSession?.userId || !session_id) return;

    try {
      await approveDeviceSession(session_id, userSession.userId);
    } catch {
      // Session may have expired, redirect will show appropriate state
    }
    // Redirect back to plugin — the plugin page will do the token exchange
    redirect("/plugin?context=plugin");
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">Studio AI</h1>
          <p className="text-muted-foreground">
            Your FL Studio plugin is requesting access to your account.
          </p>
        </div>
        <div className="rounded-lg border p-4 text-sm text-left space-y-1">
          <p><strong>Account:</strong> {userSession.user?.email}</p>
          <p><strong>Access:</strong> Control your DAW via Studio AI</p>
        </div>
        <form action={approve}>
          <button
            type="submit"
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Authorize Plugin
          </button>
        </form>
        <p className="text-xs text-muted-foreground">
          This will allow the Studio AI plugin to act on your behalf.
        </p>
      </div>
    </div>
  );
}
