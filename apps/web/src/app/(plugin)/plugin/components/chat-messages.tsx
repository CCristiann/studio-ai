"use client";

import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { isToolUIPart, getToolName } from "ai";
import type { UIMessage } from "ai";

export function ChatMessages({
  messages,
  isLoading,
  error,
}: {
  messages: UIMessage[];
  isLoading: boolean;
  error: Error | undefined;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-b from-neutral-200 to-neutral-400 text-sm font-bold text-black">
            AI
          </div>
          <p className="text-sm text-[#555]">
            Tell me what to do in your DAW.
          </p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1">
      <div className="space-y-5 px-6 py-5">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-3 ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {message.role === "assistant" && (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-gradient-to-b from-neutral-200 to-neutral-400 text-[10px] font-bold text-black">
                AI
              </div>
            )}
            <div className="max-w-[85%]">
              {message.parts.map((part, i) => {
                if (part.type === "text") {
                  return (
                    <div
                      key={i}
                      className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                        message.role === "user"
                          ? "bg-white/[0.08] text-[#f0f0f0]"
                          : "bg-white/[0.04] text-[#c8c8c8]"
                      }`}
                    >
                      {part.text}
                    </div>
                  );
                }

                if (isToolUIPart(part)) {
                  const toolName = getToolName(part);
                  const toolPart = part as {
                    type: string;
                    state: string;
                    input?: unknown;
                    output?: unknown;
                  };
                  return (
                    <div
                      key={i}
                      className="mt-2 rounded-xl border border-green-500/10 bg-green-500/[0.04] px-3.5 py-2.5 font-mono text-[11.5px] leading-relaxed"
                    >
                      <div className="text-[#666]">
                        {toolName}(
                        {toolPart.input !== undefined
                          ? JSON.stringify(toolPart.input)
                          : ""}
                        )
                      </div>
                      {toolPart.state === "output-available" &&
                        toolPart.output !== undefined && (
                          <div className="mt-1 text-green-400">
                            &#10003; {JSON.stringify(toolPart.output)}
                          </div>
                        )}
                    </div>
                  );
                }

                return null;
              })}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-gradient-to-b from-neutral-200 to-neutral-400 text-[10px] font-bold text-black">
              AI
            </div>
            <div className="rounded-2xl bg-white/[0.04] px-4 py-3">
              <div className="flex items-center gap-2 text-[13px] text-[#555]">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                Thinking...
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mx-auto max-w-sm rounded-xl border border-red-500/10 bg-red-500/[0.04] px-4 py-3 text-center text-[13px] text-red-400">
            {error.message}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
