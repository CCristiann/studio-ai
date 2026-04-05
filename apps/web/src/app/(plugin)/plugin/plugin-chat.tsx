"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, isToolUIPart, getToolName } from "ai";
import { useRef, useEffect, useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

export function PluginChat({
  token,
  onAuthError,
}: {
  token: string;
  onAuthError: () => void;
}) {
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
      // On any error, re-validate the token — if revoked, trigger logout
      try {
        const res = await fetch("/api/auth/plugin/validate", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) onAuthError();
      } catch {
        // Network error — don't force logout on transient failures
      }
    },
  });
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isLoading = status === "streaming" || status === "submitted";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendMessage({ text: input });
    setInput("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-muted-foreground">
              <h2 className="text-lg font-semibold">Studio AI</h2>
              <p className="mt-1 text-sm">
                Tell me what to do in your DAW. Try &quot;Set the BPM to
                128&quot; or &quot;Show me the project state&quot;.
              </p>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <Card
              className={`max-w-[80%] px-4 py-3 ${
                message.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              }`}
            >
              {message.parts.map((part, i) => {
                if (part.type === "text") {
                  return (
                    <div key={i} className="text-sm whitespace-pre-wrap">
                      {part.text}
                    </div>
                  );
                }

                if (isToolUIPart(part)) {
                  const toolName = getToolName(part);
                  const toolPart = part as {
                    type: string;
                    toolName?: string;
                    state: string;
                    input?: unknown;
                    output?: unknown;
                  };
                  return (
                    <div
                      key={i}
                      className="mt-2 rounded border bg-background/50 p-2 text-xs"
                    >
                      <div className="font-mono text-muted-foreground">
                        {toolName}(
                        {toolPart.input !== undefined
                          ? JSON.stringify(toolPart.input)
                          : ""}
                        )
                      </div>
                      {toolPart.state === "output-available" &&
                        toolPart.output !== undefined && (
                          <div className="mt-1 font-mono">
                            {JSON.stringify(toolPart.output)}
                          </div>
                        )}
                    </div>
                  );
                }

                return null;
              })}
            </Card>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <Card className="bg-muted px-4 py-3">
              <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                <div className="h-2 w-2 animate-pulse rounded-full bg-current" />
                <span>Thinking...</span>
              </div>
            </Card>
          </div>
        )}

        {error && (
          <div className="flex justify-center">
            <Card className="border-destructive bg-destructive/10 px-4 py-3">
              <p className="text-sm text-destructive">
                Error: {error.message}
              </p>
            </Card>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="border-t p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Tell your DAW what to do..."
            disabled={isLoading}
            className="flex-1"
            autoFocus
          />
          <Button type="submit" disabled={isLoading || !input.trim()}>
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
