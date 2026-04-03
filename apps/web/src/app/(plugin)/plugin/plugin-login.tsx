"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function PluginLogin() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const startAuth = async () => {
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/auth/device", { method: "POST" });
      if (!res.ok) {
        setError("Failed to start authentication.");
        setLoading(false);
        return;
      }

      const { session_id, device_code } = await res.json();

      // Store device session in localStorage for token exchange after redirect back
      localStorage.setItem(
        "studio-ai-pending-auth",
        JSON.stringify({ session_id, device_code })
      );

      // Redirect WebView to authorize page (will redirect to Google OAuth if needed)
      window.location.href = `/auth/device/authorize?session_id=${session_id}`;
    } catch {
      setError("Connection error. Is the server running?");
      setLoading(false);
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

        <Button onClick={startAuth} className="w-full" disabled={loading}>
          {loading ? "Redirecting..." : "Sign in with Google"}
        </Button>

        {error && (
          <p className="text-sm text-destructive text-center">{error}</p>
        )}
      </Card>
    </div>
  );
}
