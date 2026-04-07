"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PluginSidebar, type PanelId } from "./components/plugin-sidebar";
import { PluginTopbar } from "./components/plugin-topbar";
import { ChatMessages } from "./components/chat-messages";
import { ChatInput } from "./components/chat-input";
import { ConnectionPanel } from "./components/panels/connection-panel";
import { PresetsPanel } from "./components/panels/presets-panel";
import { SettingsPanel } from "./components/panels/settings-panel";
import { HelpPanel } from "./components/panels/help-panel";
import { OnboardingWizard } from "./components/onboarding-wizard";

export function PluginDashboard({
  token,
  onAuthError,
}: {
  token: string;
  onAuthError: () => void;
}) {
  const [activePanel, setActivePanel] = useState<PanelId>("chat");
  const [input, setInput] = useState("");
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<
    "connected" | "partial" | "disconnected"
  >("disconnected");
  const [pluginStatus, setPluginStatus] = useState<{
    cloud: { connected: boolean; latency_ms?: number };
    bridge: { connected: boolean; daw?: string; project?: string };
  } | null>(null);

  // Token expiry for settings panel
  const tokenExpiry = useMemo(() => {
    try {
      const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const payload = JSON.parse(atob(base64));
      return payload.exp ? new Date(payload.exp * 1000) : null;
    } catch {
      return null;
    }
  }, [token]);

  // Chat setup
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai/execute",
        headers: { Authorization: `Bearer ${token}` },
      }),
    [token]
  );

  const { messages, sendMessage, status, error } = useChat({
    transport,
    async onError() {
      try {
        const res = await fetch("/api/auth/plugin/validate", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) onAuthError();
      } catch {
        // Network error — don't force logout
      }
    },
  });

  const isLoading = status === "streaming" || status === "submitted";

  const handleSubmit = useCallback(() => {
    if (!input.trim()) return;
    sendMessage({ text: input });
    setInput("");
  }, [input, sendMessage]);

  const handleSendPrompt = useCallback(
    (prompt: string) => {
      sendMessage({ text: prompt });
      setActivePanel("chat");
    },
    [sendMessage]
  );

  const handleSignOut = useCallback(() => {
    localStorage.removeItem("studio-ai-token");
    onAuthError();
  }, [onAuthError]);

  // Check onboarding status
  useEffect(() => {
    fetch("/api/plugin/preferences", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.preferences?.onboarding_completed) {
          setShowOnboarding(true);
        }
      })
      .catch(() => {});
  }, [token]);

  // Request connection status from plugin
  const requestConnectionStatus = useCallback(() => {
    if (typeof window.sendToPlugin === "function") {
      window.sendToPlugin({ type: "getConnectionStatus" });
    } else {
      // Dev fallback: mock data
      setPluginStatus({
        cloud: { connected: true, latency_ms: 42 },
        bridge: { connected: false },
      });
    }
  }, []);

  // Single IPC handler — dashboard owns all plugin messages
  useEffect(() => {
    window.onPluginMessage = (msg) => {
      if (msg.type === "connectionStatus" && msg.payload) {
        const s = msg.payload as unknown as typeof pluginStatus;
        if (!s) return;
        setPluginStatus(s);
        if (s.cloud.connected && s.bridge.connected) {
          setConnectionStatus("connected");
        } else if (s.cloud.connected || s.bridge.connected) {
          setConnectionStatus("partial");
        } else {
          setConnectionStatus("disconnected");
        }
      }
    };

    // Initial request + polling
    requestConnectionStatus();
    const interval = setInterval(requestConnectionStatus, 5000);
    return () => clearInterval(interval);
  }, [requestConnectionStatus]);

  // Render expanded panel content
  const panelContent: Record<PanelId, React.ReactNode> = {
    chat: (
      <div className="p-3">
        <div className="text-[11px] font-medium uppercase tracking-wide text-[#444] px-1">
          Chat History
        </div>
        <div className="mt-2 text-[12px] text-[#333] px-1">
          Coming soon — multiple conversations per workspace.
        </div>
      </div>
    ),
    connection: <ConnectionPanel status={pluginStatus} onRefresh={requestConnectionStatus} />,
    presets: <PresetsPanel token={token} onSendPrompt={handleSendPrompt} />,
    settings: (
      <SettingsPanel
        tokenExpiry={tokenExpiry}
        onSignOut={handleSignOut}
        onRefreshToken={() => {
          handleSignOut();
        }}
      />
    ),
    help: (
      <HelpPanel
        onSendPrompt={handleSendPrompt}
        onReplayOnboarding={() => setShowOnboarding(true)}
      />
    ),
  };

  return (
    <TooltipProvider delay={0}>
      <SidebarProvider defaultOpen={false} style={{ "--sidebar-width": "320px", "--sidebar-width-icon": "60px" } as React.CSSProperties}>
        <PluginSidebar
          activePanel={activePanel}
          onPanelChange={setActivePanel}
          onSignOut={handleSignOut}
          connectionStatus={connectionStatus}
          panelContent={panelContent[activePanel]}
        />

        <SidebarInset className="bg-[#111] flex flex-col min-w-0">
          <PluginTopbar
            projectName={pluginStatus?.bridge.project}
            dawName={pluginStatus?.bridge.daw}
            isConnected={pluginStatus?.bridge.connected ?? false}
          />
          <ChatMessages
            messages={messages}
            isLoading={isLoading}
            error={error}
          />
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            disabled={isLoading}
          />
        </SidebarInset>
      </SidebarProvider>

      <OnboardingWizard
        open={showOnboarding}
        onComplete={() => setShowOnboarding(false)}
        token={token}
      />
    </TooltipProvider>
  );
}
