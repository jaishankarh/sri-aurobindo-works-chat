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
      {/* Connection status bar. The socket is only open while a response is
          streaming or actively connecting — it's expected to sit idle
          ("disconnected") between messages, so that state is shown neutrally
          rather than as an error; sendQuery reconnects transparently. */}
      <div
        className={clsx(
          "flex items-center gap-2 px-4 py-1.5 text-xs font-medium transition-all",
          connectionState === "connected"
            ? "bg-emerald-50 text-emerald-700"
            : connectionState === "connecting"
            ? "bg-amber-50 text-amber-700"
            : "bg-stone-100 text-stone-500"
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
            : "Ready"}
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

      {/* Input. Not gated on connectionState === "connected" — the socket is
          expected to be idle/disconnected between messages, and sendQuery
          opens a fresh connection on demand. Only block submission while a
          connection attempt is actively in flight, to avoid a double-send race. */}
      <ChatInput
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
        disabled={connectionState === "connecting"}
      />
    </div>
  );
}
