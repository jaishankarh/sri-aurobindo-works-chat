/**
 * User settings state store (Zustand).
 *
 * Manages global retrieval settings that are sent with every query:
 * - alpha: dense/sparse retrieval balance
 * - language_filter: which languages to include in retrieval
 * - selected_document_ids: filter retrieval to specific PDFs
 * - llm_model: which LLM to use for synthesis
 *
 * Settings are persisted to localStorage for session continuity.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Document, UserSettings } from "@/types";

interface SettingsStore {
  settings: UserSettings;
  availableDocuments: Document[];
  isSettingsOpen: boolean;

  // Actions
  updateSettings: (updates: Partial<UserSettings>) => void;
  setAlpha: (alpha: number) => void;
  toggleLanguage: (lang: string) => void;
  toggleDocument: (docId: string) => void;
  selectAllDocuments: () => void;
  clearDocumentSelection: () => void;
  setAvailableDocuments: (docs: Document[]) => void;
  toggleSettingsPanel: () => void;
  resetToDefaults: () => void;
}

const DEFAULT_SETTINGS: UserSettings = {
  alpha: 0.7,
  top_k: 5,
  graph_hops: 2,
  language_filter: ["en", "fr", "sa"],
  selected_document_ids: [],
  llm_model: "llama3.2",
};

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set, get) => ({
      settings: { ...DEFAULT_SETTINGS },
      availableDocuments: [],
      isSettingsOpen: false,

      updateSettings: (updates) =>
        set((state) => ({
          settings: { ...state.settings, ...updates },
        })),

      setAlpha: (alpha) =>
        set((state) => ({
          settings: { ...state.settings, alpha: Math.max(0, Math.min(1, alpha)) },
        })),

      toggleLanguage: (lang) =>
        set((state) => {
          const current = state.settings.language_filter;
          const updated = current.includes(lang)
            ? current.filter((l) => l !== lang)
            : [...current, lang];
          // Always keep at least one language enabled
          if (updated.length === 0) return state;
          return { settings: { ...state.settings, language_filter: updated } };
        }),

      toggleDocument: (docId) =>
        set((state) => {
          const current = state.settings.selected_document_ids;
          const updated = current.includes(docId)
            ? current.filter((id) => id !== docId)
            : [...current, docId];
          return { settings: { ...state.settings, selected_document_ids: updated } };
        }),

      selectAllDocuments: () =>
        set((state) => ({
          settings: {
            ...state.settings,
            selected_document_ids: state.availableDocuments.map((d) => d.id),
          },
        })),

      clearDocumentSelection: () =>
        set((state) => ({
          settings: { ...state.settings, selected_document_ids: [] },
        })),

      setAvailableDocuments: (docs) => set({ availableDocuments: docs }),

      toggleSettingsPanel: () =>
        set((state) => ({ isSettingsOpen: !state.isSettingsOpen })),

      resetToDefaults: () =>
        set({ settings: { ...DEFAULT_SETTINGS } }),
    }),
    {
      name: "aurobindo-rag-settings",
      partialize: (state) => ({ settings: state.settings }),
    }
  )
);
