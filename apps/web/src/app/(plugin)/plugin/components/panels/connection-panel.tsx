"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { Globe, Cable, RefreshCw } from "lucide-react";

interface ConnectionStatus {
  cloud: { connected: boolean; latency_ms?: number };
  bridge: { connected: boolean; daw?: string; project?: string };
}

export function ConnectionPanel({
  status,
  onRefresh,
}: {
  status: ConnectionStatus | null;
  onRefresh: () => void;
}) {
  if (!status) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  const items = [
    {
      label: "Cloud Relay",
      icon: Globe,
      connected: status.cloud.connected,
      detail: status.cloud.latency_ms ? `${status.cloud.latency_ms}ms` : undefined,
    },
    {
      label: "DAW Bridge",
      icon: Cable,
      connected: status.bridge.connected,
      detail: status.bridge.daw
        ? `${status.bridge.daw}${status.bridge.project ? ` — ${status.bridge.project}` : ""}`
        : undefined,
    },
  ];

  return (
    <div className="space-y-2 p-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-3.5 py-3"
        >
          <item.icon className="h-4 w-4 text-[#555]" />
          <div className="flex-1">
            <div className="text-[12.5px] font-medium text-[#c8c8c8]">
              {item.label}
            </div>
            {item.detail && (
              <div className="text-[10.5px] text-[#444]">{item.detail}</div>
            )}
          </div>
          <div
            className={`h-2 w-2 rounded-full ${
              item.connected
                ? "bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.4)]"
                : "bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]"
            }`}
          />
        </div>
      ))}
      <button
        onClick={onRefresh}
        className="flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] text-[#444] transition-colors hover:text-[#666]"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Refresh
      </button>
    </div>
  );
}
