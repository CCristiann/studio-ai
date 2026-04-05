"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function PluginLogin({ onToken }: { onToken: (token: string) => void }) {
  const [loading, setLoading] = useState(false);
  const [userCode, setUserCode] = useState("");
  const [error, setError] = useState("");
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  // Clean up polling on unmount
  useEffect(() => {
    return () => stopPolling();
  }, []);

  const startAuth = async () => {
    setLoading(true);
    setError("");
    setUserCode("");

    try {
      const res = await fetch("/api/auth/device", { method: "POST" });
      if (!res.ok) {
        setError("Failed to start authentication.");
        setLoading(false);
        return;
      }

      const { session_id, device_code, user_code, expires_in } = await res.json();

      setUserCode(user_code);

      // Open system browser to /link (no session_id in URL)
      const origin = window.location.origin;
      const linkUrl = `${origin}/link`;

      if (typeof window.sendToPlugin === "function") {
        window.sendToPlugin({ type: "open_browser", payload: { url: linkUrl } });
      } else {
        window.open(linkUrl, "_blank");
      }

      // Poll for token
      const deadline = Date.now() + expires_in * 1000;

      pollingRef.current = setInterval(async () => {
        if (Date.now() > deadline) {
          stopPolling();
          setError("Authorization expired. Please try again.");
          setLoading(false);
          setUserCode("");
          return;
        }

        try {
          const tokenRes = await fetch("/api/auth/device/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id, device_code }),
          });

          if (!tokenRes.ok) return;

          const data = await tokenRes.json();

          if (data.status === "complete" && data.token) {
            stopPolling();
            onToken(data.token);
          } else if (data.status === "expired") {
            stopPolling();
            setError("Session expired. Please try again.");
            setLoading(false);
            setUserCode("");
          }
        } catch {
          // Network error, keep polling
        }
      }, 2000);
    } catch {
      setError("Connection error. Is the server running?");
      setLoading(false);
      setUserCode("");
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-background">
      <Card className="w-full max-w-sm p-6 space-y-4">
        <div className="text-center space-y-1">
          <h1 className="text-xl font-semibold">Studio AI</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to connect your DAW
          </p>
        </div>

        {!userCode ? (
          <Button onClick={startAuth} className="w-full" disabled={loading}>
            {loading ? "Starting..." : "Sign in with Browser"}
          </Button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground text-center">
              Enter this code in your browser:
            </p>
            <div className="text-3xl font-mono font-bold text-center tracking-widest py-3">
              {userCode}
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Waiting for authorization...
            </p>
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive text-center">{error}</p>
        )}
      </Card>
    </div>
  );
}
