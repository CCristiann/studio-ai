"use client";

import { ExternalLink, RotateCcw } from "lucide-react";

const capabilities = [
  "Set BPM and tempo",
  "Add and rename tracks",
  "Control playback (play, stop, record)",
  "Adjust mixer (volume, pan, mute, solo)",
  "Analyze your mix",
];

const examplePrompts = [
  "Set the BPM to 128",
  "Add a new track called 'Bass'",
  "Show me the project state",
  "Set track 1 volume to 80%",
  "Stop playback",
];

export function HelpPanel({
  onSendPrompt,
  onReplayOnboarding,
}: {
  onSendPrompt: (prompt: string) => void;
  onReplayOnboarding: () => void;
}) {
  const openDocs = () => {
    if (typeof window.sendToPlugin === "function") {
      window.sendToPlugin({ type: "open_browser", payload: { url: "https://studioai.dev/docs" } });
    } else {
      window.open("https://studioai.dev/docs", "_blank");
    }
  };

  return (
    <div className="flex flex-col gap-4 p-3">
      <div>
        <div className="px-1 text-[11px] font-medium uppercase tracking-wide text-[#444]">
          Capabilities
        </div>
        <div className="mt-2 space-y-1">
          {capabilities.map((cap) => (
            <div
              key={cap}
              className="rounded-lg px-3 py-1.5 text-[12px] text-[#888]"
            >
              {cap}
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="px-1 text-[11px] font-medium uppercase tracking-wide text-[#444]">
          Try These
        </div>
        <div className="mt-2 space-y-1">
          {examplePrompts.map((prompt) => (
            <button
              key={prompt}
              onClick={() => onSendPrompt(prompt)}
              className="w-full rounded-lg px-3 py-1.5 text-left text-[12px] text-[#c8c8c8] transition-colors hover:bg-white/[0.04]"
            >
              &ldquo;{prompt}&rdquo;
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <button
          onClick={onReplayOnboarding}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] text-[#555] transition-colors hover:text-[#888]"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Replay Onboarding
        </button>
        <button
          onClick={openDocs}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] text-[#555] transition-colors hover:text-[#888]"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Documentation
        </button>
      </div>
    </div>
  );
}
