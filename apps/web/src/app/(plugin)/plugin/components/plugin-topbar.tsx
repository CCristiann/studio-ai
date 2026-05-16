"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

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
      <span className="text-[13px] font-medium tracking-tight text-foreground">
        New Chat
      </span>
      <div className="flex-1" />
      {dawName && (
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          {isConnected && (
            <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
          )}
          <span>
            {dawName}
            {projectName ? ` — ${projectName}` : ""}
          </span>
        </div>
      )}
      <Button
        variant="ghost"
        size="icon"
        className="size-7 rounded-lg"
        aria-label="New chat"
      >
        <Plus className="size-3.5" />
      </Button>
    </div>
  );
}
