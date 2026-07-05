/**
 * High-level hook for submitting RAG queries and managing session state.
 *
 * Wraps useWebSocket and integrates with all three Zustand stores:
 * - useChatStore: for message tracking
 * - useSettingsStore: for retrieval settings
 * - usePDFStore: for citation highlighting (accessed read-only here)
 */

import { useCallback, useEffect, useRef } from "react";
import { useChatStore } from "@/stores/useChatStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useWebSocket } from "./useWebSocket";

const generateMessageId = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

export function useRAGQuery() {
  const sessionId = useRef<string>(
    crypto.randomUUID ? crypto.randomUUID() : generateMessageId()
  );

  const { addUserMessage, setSessionId } = useChatStore();
  const { settings } = useSettingsStore();

  const { connectionState, sendQuery, disconnect, reconnect } = useWebSocket({
    sessionId: sessionId.current,
  });

  useEffect(() => {
    setSessionId(sessionId.current);
  }, [setSessionId]);

  const submitQuery = useCallback(
    (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) return;

      // Add user message to chat immediately
      addUserMessage(trimmed);

      const messageId = generateMessageId();

      // Send via WebSocket
      sendQuery({
        query: trimmed,
        settings,
        messageId,
      });
    },
    [addUserMessage, sendQuery, settings]
  );

  return {
    sessionId: sessionId.current,
    connectionState,
    submitQuery,
    disconnect,
    reconnect,
  };
}
