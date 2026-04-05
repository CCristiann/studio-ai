"use client";

import { Button } from "@/components/ui/button";
import { LogOut, Key } from "lucide-react";

export function SettingsPanel({
  tokenExpiry,
  onSignOut,
  onRefreshToken,
}: {
  tokenExpiry: Date | null;
  onSignOut: () => void;
  onRefreshToken: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="rounded-xl bg-white/[0.02] px-3.5 py-3">
        <div className="flex items-center gap-2">
          <Key className="h-4 w-4 text-[#555]" />
          <div className="flex-1">
            <div className="text-[12.5px] font-medium text-[#c8c8c8]">
              Session Token
            </div>
            <div className="text-[10.5px] text-[#444]">
              {tokenExpiry
                ? `Expires ${tokenExpiry.toLocaleDateString()} at ${tokenExpiry.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : "Active"}
            </div>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefreshToken}
          className="mt-2 w-full text-[11px] text-[#555] hover:text-[#888]"
        >
          Refresh Token
        </Button>
      </div>

      <Button
        variant="ghost"
        onClick={onSignOut}
        className="w-full justify-start gap-2 rounded-xl px-3.5 py-3 text-[12.5px] text-red-400 hover:bg-red-500/5 hover:text-red-300"
      >
        <LogOut className="h-4 w-4" />
        Sign Out
      </Button>
    </div>
  );
}
