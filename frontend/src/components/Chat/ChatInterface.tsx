import { useEffect, useCallback } from "react";
import { clsx } from "clsx";
import { useChatStore } from "@/stores/useChatStore";
import { useRAGQuery } from "@/hooks/useRAGQuery";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { Wifi, WifiOff, AlertCircle, X } from "lucide-react";

export function ChatInterface() {
  const { connectionState, submitQuery } = useRAGQuery();
  const { streamingMessageId, error, clearError } = useChatStore();

  const isStreaming = streamingMessageId !== null;

  // Listen for suggestion click events from MessageList
  useEffect(() => {
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<{ query: string }>;
      if (!isStreaming) {
        submitQuery(customEvent.detail.query);
      }
    };
    window.addEventListener("rag:suggestion", handler);
    return () => window.removeEventListener("rag:suggestion", handler);
  }, [submitQuery, isStreaming]);

  const handleSubmit = useCallback(
    (query: string) => {
      submitQuery(query);
    },
    [submitQuery]
  );

  return (
    <div className="flex h-full flex-col bg-stone-50">
      {/* Connection status bar */}
      <div
        className={clsx(
          "flex items-center gap-2 px-4 py-1.5 text-xs font-medium transition-all",
          connectionState === "connected"
            ? "bg-emerald-50 text-emerald-700"
            : connectionState === "connecting"
            ? "bg-amber-50 text-amber-700"
            : "bg-red-50 text-red-700"
        )}
      >
        {connectionState === "connected" ? (
          <Wifi className="h-3 w-3" />
        ) : (
          <WifiOff className="h-3 w-3" />
        )}
        <span>
          {connectionState === "connected"
            ? "Connected"
            : connectionState === "connecting"
            ? "Connecting…"
            : "Disconnected — will retry automatically"}
        </span>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border-b border-red-200 px-4 py-2 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            onClick={clearError}
            className="flex-shrink-0 text-red-500 hover:text-red-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Messages */}
      <MessageList />

      {/* Input */}
      <ChatInput
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
        disabled={connectionState !== "connected"}
      />
    </div>
  );
}
