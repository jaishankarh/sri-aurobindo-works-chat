import { useState, useRef, useCallback, type KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";
import { clsx } from "clsx";

interface ChatInputProps {
  onSubmit: (query: string) => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSubmit,
  isStreaming,
  disabled = false,
  placeholder = "Ask about Sri Aurobindo or The Mother's teachings...",
}: ChatInputProps) {
  const [query, setQuery] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = query.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSubmit(trimmed);
    setQuery("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [query, isStreaming, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setQuery(e.target.value);
      // Auto-resize textarea
      const ta = e.target;
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    },
    []
  );

  const isDisabled = disabled || isStreaming;

  return (
    <div className="border-t border-stone-200 bg-surface px-4 py-3">
      <div
        className={clsx(
          "flex items-end gap-2 rounded-xl border bg-stone-50 px-3 py-2 transition-all",
          isDisabled
            ? "border-stone-200 opacity-60"
            : "border-stone-300 focus-within:border-amber-400 focus-within:ring-2 focus-within:ring-amber-100"
        )}
      >
        <textarea
          ref={textareaRef}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isDisabled}
          rows={1}
          className={clsx(
            "flex-1 resize-none bg-transparent text-sm text-stone-800 placeholder-stone-400 focus:outline-none",
            "min-h-[24px] max-h-[200px]"
          )}
        />
        <button
          onClick={handleSubmit}
          disabled={isDisabled || !query.trim()}
          className={clsx(
            "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg transition-all",
            query.trim() && !isDisabled
              ? "bg-amber-500 text-white hover:bg-amber-600 active:scale-95"
              : "bg-stone-200 text-stone-400 cursor-not-allowed"
          )}
          aria-label="Send message"
        >
          {isStreaming ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
      <p className="mt-1.5 text-xs text-stone-400">
        Press Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
