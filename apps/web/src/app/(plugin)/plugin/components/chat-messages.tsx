"use client";

import { useRef, useEffect } from "react";
import { isToolUIPart, getToolName } from "ai";
import type { UIMessage } from "ai";
import Markdown from "react-markdown";

export function ChatMessages({
  messages,
  isLoading,
  error,
}: {
  messages: UIMessage[];
  isLoading: boolean;
  error: Error | undefined;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-b from-neutral-200 to-neutral-400 text-sm font-bold text-black">
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
    <div className="relative flex-1 min-h-0">
      {/* Top fade */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-8 bg-linear-to-b from-[#111] to-transparent" />

      <div
        ref={scrollRef}
        className="h-full overflow-y-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10"
      >
        <div className="space-y-5 px-6 py-5">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"
                }`}
            >
              <div className="max-w-2xl">
                {message.parts.map((part, i) => {
                  if (part.type === "text") {
                    return (
                      <div
                        key={i}
                        className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${message.role === "user"
                          ? "bg-white/[0.08] text-[#f0f0f0]"
                          : "bg-white/[0.04] text-[#c8c8c8]"
                          }`}
                      >
                        {message.role === "user" ? (
                          part.text
                        ) : (
                          <Markdown
                            components={{
                              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                              strong: ({ children }) => <strong className="font-semibold text-[#e0e0e0]">{children}</strong>,
                              ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">{children}</ul>,
                              ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">{children}</ol>,
                              li: ({ children }) => <li>{children}</li>,
                              h1: ({ children }) => <h1 className="mb-1 text-sm font-semibold text-[#e0e0e0]">{children}</h1>,
                              h2: ({ children }) => <h2 className="mb-1 text-sm font-semibold text-[#e0e0e0]">{children}</h2>,
                              h3: ({ children }) => <h3 className="mb-1 text-[13px] font-semibold text-[#e0e0e0]">{children}</h3>,
                              code: ({ children }) => <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[11.5px] text-[#e0e0e0]">{children}</code>,
                              pre: ({ children }) => <pre className="mb-2 overflow-x-auto rounded-lg bg-black/30 p-2.5 font-mono text-[11.5px] last:mb-0">{children}</pre>,
                            }}
                          >
                            {part.text}
                          </Markdown>
                        )}
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
            <div className="rounded-2xl bg-white/[0.04] px-4 py-3">
              <div className="flex items-center gap-2 text-[13px] text-[#555]">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                Thinking...
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
      </div>

      {/* Bottom fade */}
      <div className="pointer-events-none absolute inset-x-0 -bottom-0.5 z-10 h-8 bg-linear-to-t from-[#111] to-transparent" />
    </div>
  );
}
