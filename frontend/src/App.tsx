/**
 * Main application layout.
 *
 * Chat is the only pane in the base layout and always takes the full width.
 * The PDF viewer and settings panel are both slide-in overlays (Radix Dialog)
 * that mount unconditionally but render nothing until opened — PDFViewer
 * opens itself when usePDFStore.currentDocumentPath is set (a citation was
 * clicked); SettingsPanel opens via the header button. Neither takes up
 * layout space while closed.
 *
 * ┌─────────────────────────────────────────────────────┐
 * │  Header (title + settings button)                   │
 * ├───────────────────────────────────────────────────────┤
 * │                                                       │
 * │   Chat Interface (full width)                        │
 * │   (useChatStore)                                     │
 * │                                                       │
 * │   Messages stream here without affecting the PDF     │
 * │   canvas, which lives in its own overlay and only    │
 * │   subscribes to usePDFStore.                         │
 * │                                                       │
 * └─────────────────────────────────────────────────────┘
 *
 * The strict Zustand store separation ensures that LLM token streaming
 * (useChatStore) does not trigger PDF canvas re-renders (usePDFStore).
 */

import { useCallback } from "react";
import { Settings } from "lucide-react";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { usePDFStore } from "@/stores/usePDFStore";
import { ChatInterface } from "@/components/Chat/ChatInterface";
import { PDFViewer } from "@/components/PDFViewer/PDFViewer";
import { SettingsPanel } from "@/components/Settings/SettingsPanel";

export default function App() {
  const toggleSettings = useSettingsStore((s) => s.toggleSettingsPanel);

  const handleLogoClick = useCallback(() => {
    usePDFStore.getState().loadDocument("");
  }, []);

  return (
    <div className="flex h-full flex-col bg-surface">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-stone-200 bg-surface px-4 py-2.5 shadow-sm z-10">
        <div
          className="flex items-center gap-2 cursor-pointer"
          onClick={handleLogoClick}
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-500">
            <span className="text-white font-bold text-sm">✦</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-stone-800 leading-tight">
              Sri Aurobindo & The Mother
            </h1>
            <p className="text-xs text-stone-400 leading-tight">
              Complete Works Explorer
            </p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-stone-400 hidden sm:block">
            Multilingual RAG · English · Français · Sanskrit
          </span>
          <button
            onClick={toggleSettings}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 hover:border-stone-300 transition-all"
            aria-label="Open retrieval settings"
            title="Retrieval Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Chat: the only pane, always full width */}
      <main className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 min-w-0 flex-col overflow-hidden">
          <ChatInterface />
        </div>
      </main>

      {/* Overlay panels — mounted unconditionally, each manages its own open state */}
      <PDFViewer />
      <SettingsPanel />
    </div>
  );
}
