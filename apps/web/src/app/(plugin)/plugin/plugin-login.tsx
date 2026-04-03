"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type AuthState = "idle" | "waiting" | "complete" | "expired" | "error";

export function PluginLogin({
  onToken,
}: {
  onToken: (token: string) => void;
}) {
  const [state, setState] = useState<AuthState>("idle");
  const [error, setError] = useState("");

  const startAuth = useCallback(async () => {
    setState("waiting");
    setError("");

    try {
      const res = await fetch("/api/auth/device", { method: "POST" });
      if (!res.ok) {
        setState("error");
        setError("Failed to start authentication.");
        return;
      }

      const { session_id, device_code, interval } = await res.json();

      // Open system browser for authorization
      window.open(
        `${window.location.origin}/auth/device/authorize?session_id=${session_id}`,
        "_blank"
      );

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const pollRes = await fetch("/api/auth/device/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id, device_code }),
          });

          if (!pollRes.ok) {
            clearInterval(pollInterval);
            setState("error");
            setError("Authentication failed. Please try again.");
            return;
          }

          const data = await pollRes.json();

          if (data.status === "complete") {
            clearInterval(pollInterval);
            localStorage.setItem("studio-ai-token", data.token);
            setState("complete");
            onToken(data.token);
          } else if (data.status === "expired") {
            clearInterval(pollInterval);
            setState("expired");
          }
        } catch {
          // Network error — continue polling
        }
      }, (interval || 2) * 1000);

      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setState((current) => (current === "waiting" ? "expired" : current));
      }, 5 * 60 * 1000);
    } catch {
      setState("error");
      setError("Connection error. Is the server running?");
    }
  }, [onToken]);

  return (
    <div className="flex h-full items-center justify-center bg-background">
      <Card className="w-full max-w-sm p-6 space-y-4">
        <div className="text-center space-y-1">
          <h1 className="text-xl font-semibold">Studio AI</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to connect your DAW
          </p>
        </div>

        {state === "idle" && (
          <Button onClick={startAuth} className="w-full">
            Sign in with Google
          </Button>
        )}

        {state === "waiting" && (
          <div className="space-y-3 text-center">
            <div className="flex items-center justify-center space-x-2">
              <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              <span className="text-sm text-muted-foreground">
                Waiting for authorization...
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Complete sign-in in the browser window that just opened.
            </p>
          </div>
        )}

        {state === "expired" && (
          <div className="space-y-3">
            <p className="text-sm text-center text-muted-foreground">
              Authorization expired. Please try again.
            </p>
            <Button onClick={startAuth} className="w-full" variant="outline">
              Try again
            </Button>
          </div>
        )}

        {state === "error" && (
          <div className="space-y-3">
            <p className="text-sm text-destructive text-center">{error}</p>
            <Button onClick={startAuth} className="w-full" variant="outline">
              Try again
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
