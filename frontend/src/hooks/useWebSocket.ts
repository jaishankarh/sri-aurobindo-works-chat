/**
 * WebSocket hook for real-time RAG streaming.
 *
 * Implements the client side of the Replay-then-Tail protocol:
 * - Sends queries to the backend WebSocket
 * - Tracks the last seen Redis stream ID for reconnect recovery
 * - Automatically reconnects on disconnect using exponential backoff
 * - Dispatches events to useChatStore without touching usePDFStore
 *   (chat tokens must never trigger PDF canvas re-renders)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useChatStore } from "@/stores/useChatStore";
import { usePDFStore } from "@/stores/usePDFStore";
import type { UserSettings, WSEvent } from "@/types";

const WS_BASE_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 1000;

interface UseWebSocketOptions {
  sessionId: string;
}

interface SendQueryOptions {
  query: string;
  settings: UserSettings;
  messageId: string;
}

export function useWebSocket({ sessionId }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connectionState, setConnectionState] = useState<
    "disconnected" | "connecting" | "connected"
  >("disconnected");

  const {
    startStreaming,
    appendToken,
    setStreamingStatus,
    finalizeStreaming,
    setError,
    setConnected,
    setLastSeenStreamId,
    lastSeenStreamId,
  } = useChatStore();

  const { addHighlights, jumpToCitation } = usePDFStore();

  const handleEvent = useCallback(
    (event: WSEvent) => {
      switch (event.type) {
        case "status":
          setStreamingStatus(event.data.status);
          break;

        case "token":
          appendToken(event.data);
          // Track stream position for reconnect recovery
          if ("_stream_id" in event) {
            setLastSeenStreamId((event as unknown as { _stream_id: string })._stream_id);
          }
          break;

        case "citation":
          if (event.data.citations.length > 0) {
            addHighlights(event.data.citations);
          }
          break;

        case "complete":
          // Finalize the streaming message with all accumulated citations
          const { highlights } = usePDFStore.getState();
          finalizeStreaming(highlights.map((h) => h.citation));
          break;

        case "error":
          setError(event.data.error);
          break;
      }
    },
    [appendToken, setStreamingStatus, finalizeStreaming, setError, addHighlights, setLastSeenStreamId]
  );

  const connect = useCallback(
    (isReconnect = false) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      setConnectionState("connecting");
      const url = `${WS_BASE_URL}/api/v1/chat/ws/${sessionId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnectionState("connected");
        setConnected(true);
        reconnectAttempts.current = 0;

        if (isReconnect) {
          // Send reconnect message with last known stream position
          ws.send(
            JSON.stringify({
              type: "reconnect",
              last_seen_id: lastSeenStreamId,
            })
          );
        }
      };

      ws.onmessage = (e) => {
        try {
          const event: WSEvent = JSON.parse(e.data);
          handleEvent(event);
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onclose = () => {
        setConnectionState("disconnected");
        setConnected(false);
        wsRef.current = null;

        // Exponential backoff reconnection
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          const delay =
            RECONNECT_BASE_DELAY_MS *
            Math.pow(2, reconnectAttempts.current);
          reconnectAttempts.current++;
          reconnectTimerRef.current = setTimeout(() => connect(true), delay);
        }
      };

      ws.onerror = (e) => {
        console.error("WebSocket error:", e);
      };
    },
    [sessionId, lastSeenStreamId, handleEvent, setConnected]
  );

  const sendQuery = useCallback(
    ({ query, settings, messageId }: SendQueryOptions) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        setError("Not connected. Please wait for reconnection.");
        return;
      }

      startStreaming(messageId);

      wsRef.current.send(
        JSON.stringify({
          type: "query",
          query,
          session_id: sessionId,
          settings: settings,
          last_seen_id: "0",
        })
      );
    },
    [sessionId, startStreaming, setError]
  );

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    reconnectAttempts.current = MAX_RECONNECT_ATTEMPTS; // prevent auto-reconnect
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    connect(false);
    return () => disconnect();
  }, [sessionId]); // reconnect when session changes

  return {
    connectionState,
    sendQuery,
    disconnect,
    reconnect: () => {
      reconnectAttempts.current = 0;
      connect(true);
    },
  };
}
