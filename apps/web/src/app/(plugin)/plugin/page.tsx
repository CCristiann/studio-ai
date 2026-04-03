"use client";

import { useEffect, useState, useCallback } from "react";
import { PluginChat } from "./plugin-chat";
import { PluginLogin } from "./plugin-login";

export default function PluginPage() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("studio-ai-token");
    if (stored) {
      // Quick client-side expiry check (JWT payload is base64url)
      try {
        const base64 = stored.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
        const payload = JSON.parse(atob(base64));
        if (payload.exp && payload.exp * 1000 > Date.now()) {
          setToken(stored);
        } else {
          localStorage.removeItem("studio-ai-token");
        }
      } catch {
        localStorage.removeItem("studio-ai-token");
      }
    }
    setReady(true);
  }, []);

  const handleToken = useCallback((newToken: string) => {
    setToken(newToken);
  }, []);

  if (!ready) return null;

  if (!token) {
    return <PluginLogin onToken={handleToken} />;
  }

  return <PluginChat token={token} />;
}
