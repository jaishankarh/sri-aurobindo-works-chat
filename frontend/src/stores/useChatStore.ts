/**
 * Chat state store (Zustand).
 *
 * CRITICAL: This store is intentionally separated from usePDFStore and
 * useSettingsStore. Streaming LLM tokens update this store at high frequency
 * (potentially 50+ times/second). Placing PDF viewer state here would cause
 * the heavy PDF canvas to re-render on every single token, crashing the browser.
 *
 * Only components that need chat data should subscribe to this store.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type { ChatMessage, Citation, WSEvent } from "@/types";

interface ChatStore {
  // State
  messages: ChatMessage[];
  streamingMessageId: string | null;
  streamingContent: string;
  streamingStatus: string | null;
  sessionId: string | null;
  isConnected: boolean;
  error: string | null;
  lastSeenStreamId: string;

  // Actions
  setSessionId: (id: string) => void;
  addUserMessage: (query: string) => ChatMessage;
  startStreaming: (messageId: string) => void;
  appendToken: (token: string) => void;
  setStreamingStatus: (status: string) => void;
  finalizeStreaming: (citations: Citation[]) => void;
  setError: (error: string) => void;
  setConnected: (connected: boolean) => void;
  setLastSeenStreamId: (id: string) => void;
  clearError: () => void;
  reset: () => void;
}

const generateId = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

export const useChatStore = create<ChatStore>()(
  subscribeWithSelector((set, get) => ({
    messages: [],
    streamingMessageId: null,
    streamingContent: "",
    streamingStatus: null,
    sessionId: null,
    isConnected: false,
    error: null,
    lastSeenStreamId: "0",

    setSessionId: (id) => set({ sessionId: id }),

    addUserMessage: (query) => {
      const msg: ChatMessage = {
        id: generateId(),
        session_id: get().sessionId || "",
        role: "user",
        content: query,
        citations: [],
        status: "complete",
        created_at: new Date().toISOString(),
      };
      set((state) => ({ messages: [...state.messages, msg] }));
      return msg;
    },

    startStreaming: (messageId) => {
      const placeholder: ChatMessage = {
        id: messageId,
        session_id: get().sessionId || "",
        role: "assistant",
        content: "",
        citations: [],
        status: "streaming",
        created_at: new Date().toISOString(),
      };
      set((state) => ({
        messages: [...state.messages, placeholder],
        streamingMessageId: messageId,
        streamingContent: "",
        streamingStatus: "thinking",
      }));
    },

    appendToken: (token) => {
      set((state) => {
        const newContent = state.streamingContent + token;
        return {
          streamingContent: newContent,
          messages: state.messages.map((m) =>
            m.id === state.streamingMessageId
              ? { ...m, content: newContent }
              : m
          ),
        };
      });
    },

    setStreamingStatus: (status) => set({ streamingStatus: status }),

    finalizeStreaming: (citations) => {
      set((state) => ({
        messages: state.messages.map((m) =>
          m.id === state.streamingMessageId
            ? { ...m, citations, status: "complete" as const }
            : m
        ),
        streamingMessageId: null,
        streamingContent: "",
        streamingStatus: null,
      }));
    },

    setError: (error) => {
      set((state) => ({
        error,
        messages: state.messages.map((m) =>
          m.id === state.streamingMessageId
            ? { ...m, status: "error" as const }
            : m
        ),
        streamingMessageId: null,
        streamingStatus: null,
      }));
    },

    setConnected: (connected) => set({ isConnected: connected }),

    setLastSeenStreamId: (id) => set({ lastSeenStreamId: id }),

    clearError: () => set({ error: null }),

    reset: () =>
      set({
        messages: [],
        streamingMessageId: null,
        streamingContent: "",
        streamingStatus: null,
        error: null,
        lastSeenStreamId: "0",
      }),
  }))
);
