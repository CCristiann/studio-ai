"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { PluginDashboard } from "./plugin-dashboard";
import { PluginLogin } from "./plugin-login";

const STORAGE_KEY = "studio-ai-token";
const VALIDATE_INTERVAL_MS = 30_000; // 30 seconds

export default function PluginPage() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearToken = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setToken(null);
  }, []);

  // Send JWT to Rust plugin via WebView IPC so it can open the cloud WebSocket
  const sendTokenToPlugin = useCallback((jwt: string) => {
    if (typeof window.sendToPlugin === "function") {
      window.sendToPlugin({ type: "sendToken", payload: { token: jwt } });
    }
  }, []);

  const validateToken = useCallback(
    async (jwt: string): Promise<boolean> => {
      try {
        const res = await fetch("/api/auth/plugin/validate", {
          method: "POST",
          headers: { Authorization: `Bearer ${jwt}` },
        });
        if (!res.ok) {
          clearToken();
          return false;
        }
        return true;
      } catch {
        // Network error — don't clear token on transient failures
        return true;
      }
    },
    [clearToken]
  );

  // Initial mount: check stored token validity
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      setReady(true);
      return;
    }

    // Quick client-side expiry check first
    try {
      const base64 = stored.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const payload = JSON.parse(atob(base64));
      if (!payload.exp || payload.exp * 1000 <= Date.now()) {
        localStorage.removeItem(STORAGE_KEY);
        setReady(true);
        return;
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      setReady(true);
      return;
    }

    // Server-side validation (checks revocation)
    validateToken(stored).then((valid) => {
      if (valid) {
        setToken(stored);
        sendTokenToPlugin(stored);
      }
      setReady(true);
    });
  }, [validateToken, sendTokenToPlugin]);

  // Periodic validation while authenticated
  useEffect(() => {
    if (!token) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      validateToken(token);
    }, VALIDATE_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [token, validateToken]);

  const handleToken = useCallback((newToken: string) => {
    localStorage.setItem(STORAGE_KEY, newToken);
    setToken(newToken);
    sendTokenToPlugin(newToken);
  }, [sendTokenToPlugin]);

  if (!ready) return null;

  if (!token) {
    return <PluginLogin onToken={handleToken} />;
  }

  return <PluginDashboard token={token} onAuthError={clearToken} />;
}
