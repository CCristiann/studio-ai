export const dynamic = "force-dynamic";

import { headers } from "next/headers";
import { signIn } from "@/lib/auth";
import { recordAuthEvent } from "@/lib/auth-events";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; context?: string; error?: string }>;
}) {
  const params = await searchParams;

  // NextAuth redirects here with ?error=<code> on OAuth failures. Record
  // it for the audit trail. We skip prefetch requests (which trigger
  // server renders but don't represent a user actually seeing the error).
  if (params.error) {
    const hdrs = await headers();
    const isPrefetch = hdrs.get("next-router-prefetch") !== null
      || hdrs.get("purpose") === "prefetch";
    if (!isPrefetch) {
      await recordAuthEvent({
        type: "login_failed",
        success: false,
        reason: params.error,
        ip: hdrs.get("x-forwarded-for")?.split(",")[0]?.trim()
          ?? hdrs.get("x-real-ip"),
        userAgent: hdrs.get("user-agent"),
      });
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/50 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 text-2xl font-bold tracking-tight">
            Studio AI
          </div>
          <CardTitle className="text-xl">Welcome back</CardTitle>
          <CardDescription>Sign in to your account</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            action={async () => {
              "use server";
              const params = await searchParams;
              await signIn("google", {
                redirectTo: params.callbackUrl ?? "/dashboard",
              });
            }}
          >
            <Button variant="outline" type="submit" className="w-full">
              <svg className="mr-2 size-4" viewBox="0 0 24 24">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="#EA4335"
                />
              </svg>
              Continue with Google
            </Button>
          </form>
          <div className="flex items-center gap-4">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">or</span>
            <Separator className="flex-1" />
          </div>
          <p className="text-center text-xs text-muted-foreground">
            By continuing, you agree to our Terms of Service and Privacy Policy.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
