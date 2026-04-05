"use client";

import { Plus } from "lucide-react";

export function PluginTopbar({
  projectName,
  dawName,
  isConnected,
}: {
  projectName?: string;
  dawName?: string;
  isConnected: boolean;
}) {
  return (
    <div className="flex h-12 items-center gap-3 px-5">
      <span className="text-[13px] font-medium text-foreground tracking-tight">
        New Chat
      </span>
      <div className="flex-1" />
      {dawName && (
        <div className="flex items-center gap-1.5 text-[11px] text-[#3a3a3a]">
          {isConnected && (
            <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
          )}
          <span>
            {dawName}
            {projectName ? ` — ${projectName}` : ""}
          </span>
        </div>
      )}
      <button className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/[0.03] transition-colors hover:bg-white/[0.06]">
        <Plus className="h-3.5 w-3.5 text-[#555]" />
      </button>
    </div>
  );
}
