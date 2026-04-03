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
        const payload = JSON.parse(atob(stored.split(".")[1]));
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
