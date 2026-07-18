/**
 * Theme state store (Zustand, persisted to localStorage).
 *
 * Applies the active theme by setting `data-theme` on <html>; every color
 * value is then resolved via CSS custom properties defined per-theme in
 * index.css (consumed through tailwind.config.js's stone/amber/surface
 * color definitions). No component needs to know which theme is active.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export const THEMES = [
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
  { id: "sepia", label: "Sepia" },
  { id: "solarized-light", label: "Solarized Light" },
  { id: "solarized-dark", label: "Solarized Dark" },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

interface ThemeStore {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
}

function applyTheme(theme: ThemeId) {
  document.documentElement.setAttribute("data-theme", theme);
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      theme: "light",
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: "aurobindo-rag-theme",
      onRehydrateStorage: () => (state) => {
        // Apply the persisted theme to <html> once storage has rehydrated —
        // the store's initial "light" default already matches index.css's
        // :root fallback, so there's no flash before this runs.
        if (state) applyTheme(state.theme);
      },
    }
  )
);
