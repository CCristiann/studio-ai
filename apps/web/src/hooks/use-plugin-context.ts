"use client";

import { useSearchParams } from "next/navigation";

export function usePluginContext(): boolean {
  const searchParams = useSearchParams();
  return searchParams.get("context") === "plugin";
}
