/**
 * WebSocket hook for real-time RAG streaming.
 *
 * Implements the client side of the Replay-then-Tail protocol:
 * - Sends queries to the backend WebSocket
 * - Tracks the last seen Redis stream ID for reconnect recovery
 * - Automatically reconnects on disconnect using exponential backoff — but
 *   ONLY while a response is still in flight. The server closes the socket
 *   normally after every "complete"/"error" event (one connection per
 *   query/response cycle by design), so reconnecting after that would just
 *   loop forever: reconnect → replay the already-terminal event → server
 *   closes again → onclose fires → reconnect... This is gated on
 *   activeMessageIdRef, which is cleared exactly when a terminal event arrives.
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
  // The server's message_id for the response currently in flight — set on
  // every status/token/citation event, cleared on complete/error. Reconnect
  // is only attempted while this is non-null (i.e. we were cut off mid-stream).
  const activeMessageIdRef = useRef<string | null>(null);
  // A query submitted while disconnected — sent as soon as a fresh connection opens.
  const pendingQueryRef = useRef<SendQueryOptions | null>(null);
  const [connectionState, setConnectionState] = useState<
    "disconnected" | "connecting" | "connected"
  >("disconnected");

  const {
    startStreaming,
    appendToken,
    setStreamingStatus,
    setStreamingCitations,
    finalizeStreaming,
    setError,
    setConnected,
    setLastSeenStreamId,
    lastSeenStreamId,
  } = useChatStore();

  const { addHighlights } = usePDFStore();

  const handleEvent = useCallback(
    (event: WSEvent) => {
      switch (event.type) {
        case "status":
          activeMessageIdRef.current = event.message_id;
          setStreamingStatus(event.data.status, event.data.detail);
          break;

        case "token":
          activeMessageIdRef.current = event.message_id;
          appendToken(event.data);
          // Track stream position for reconnect recovery
          if ("_stream_id" in event) {
            setLastSeenStreamId((event as unknown as { _stream_id: string })._stream_id);
          }
          break;

        case "citation":
          activeMessageIdRef.current = event.message_id;
          if (event.data.citations.length > 0) {
            // Set directly on this message (not derived from usePDFStore's
            // highlights, which accumulate across the whole session).
            setStreamingCitations(event.data.citations);
            // Still feed the PDF viewer's highlight overlay separately.
            addHighlights(event.data.citations);
          }
          break;

        case "complete":
          // Terminal event — nothing left to reconnect to for this message.
          activeMessageIdRef.current = null;
          finalizeStreaming();
          break;

        case "error":
          activeMessageIdRef.current = null;
          setError(event.data.error);
          break;
      }
    },
    [
      appendToken,
      setStreamingStatus,
      setStreamingCitations,
      finalizeStreaming,
      setError,
      addHighlights,
      setLastSeenStreamId,
    ]
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

        if (isReconnect && activeMessageIdRef.current) {
          // Resume the in-flight response
          ws.send(
            JSON.stringify({
              type: "reconnect",
              message_id: activeMessageIdRef.current,
              last_seen_id: lastSeenStreamId,
            })
          );
        } else if (pendingQueryRef.current) {
          // A query was submitted while disconnected — send it now
          const { query, settings, messageId } = pendingQueryRef.current;
          pendingQueryRef.current = null;
          startStreaming(messageId);
          ws.send(
            JSON.stringify({
              type: "query",
              query,
              session_id: sessionId,
              settings,
              last_seen_id: "0",
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

        // Only reconnect if we were actually cut off mid-response — the
        // server closes normally after every completed/errored response,
        // and reconnecting to an already-terminal stream would just loop
        // forever (replay the terminal event, close, reconnect, repeat).
        if (activeMessageIdRef.current && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
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
    [sessionId, lastSeenStreamId, handleEvent, setConnected, startStreaming]
  );

  const sendQuery = useCallback(
    ({ query, settings, messageId }: SendQueryOptions) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        startStreaming(messageId);
        wsRef.current.send(
          JSON.stringify({
            type: "query",
            query,
            session_id: sessionId,
            settings,
            last_seen_id: "0",
          })
        );
        return;
      }

      // Not connected — the previous response's connection closed normally
      // and we deliberately didn't reconnect. Queue this query and open a
      // fresh connection for it.
      pendingQueryRef.current = { query, settings, messageId };
      reconnectAttempts.current = 0;
      connect(false);
    },
    [sessionId, startStreaming, connect]
  );

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    activeMessageIdRef.current = null;
    reconnectAttempts.current = MAX_RECONNECT_ATTEMPTS; // prevent auto-reconnect
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    connect(false);
    return () => disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
