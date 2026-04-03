"use client";

import { useEffect, useState } from "react";
import { PluginChat } from "./plugin-chat";
import { PluginLogin } from "./plugin-login";

export default function PluginPage() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    async function init() {
      // 1. Check for existing valid token
      const stored = localStorage.getItem("studio-ai-token");
      if (stored) {
        try {
          const base64 = stored.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
          const payload = JSON.parse(atob(base64));
          if (payload.exp && payload.exp * 1000 > Date.now()) {
            setToken(stored);
            setReady(true);
            return;
          }
        } catch {
          // Invalid token, continue
        }
        localStorage.removeItem("studio-ai-token");
      }

      // 2. Check for pending device auth (returning from authorize page)
      const pending = localStorage.getItem("studio-ai-pending-auth");
      if (pending) {
        try {
          const { session_id, device_code } = JSON.parse(pending);
          localStorage.removeItem("studio-ai-pending-auth");

          const res = await fetch("/api/auth/device/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id, device_code }),
          });

          if (res.ok) {
            const data = await res.json();
            if (data.status === "complete" && data.token) {
              localStorage.setItem("studio-ai-token", data.token);
              setToken(data.token);
              setReady(true);
              return;
            }
          }
        } catch {
          // Exchange failed, show login
        }
      }

      setReady(true);
    }

    init();
  }, []);

  if (!ready) return null;

  if (!token) {
    return <PluginLogin />;
  }

  return <PluginChat token={token} />;
}
