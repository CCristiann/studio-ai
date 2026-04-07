"use client";

import { useRef, useEffect } from "react";
import { ArrowRight } from "lucide-react";

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) onSubmit();
    }
  };

  return (
    <div className="px-5 pb-5 pt-3 max-w-2xl mx-auto w-full">
      <div className="flex items-end gap-2.5 rounded-3xl border border-white/5 bg-white/[0.03] px-5 py-1.5 transition-colors hover:border-white/10 focus-within:border-white/10">
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Studio AI anything..."
          disabled={disabled}
          rows={4}
          className="flex-1 resize-none bg-transparent py-2.5 text-[13px] leading-relaxed text-foreground placeholder:text-[#444] focus:outline-none disabled:opacity-50"
        />
        <button
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-black shadow-sm transition-transform hover:scale-105 disabled:opacity-30 disabled:hover:scale-100"
        >
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
