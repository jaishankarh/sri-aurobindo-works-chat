/**
 * Main application layout.
 *
 * Split-pane layout:
 * ┌─────────────────────────────────────────────────────┐
 * │  Header (title + settings button)                   │
 * ├──────────────────────────┬──────────────────────────┤
 * │                          │                          │
 * │   Chat Interface         │   PDF Viewer             │
 * │   (useChatStore)         │   (usePDFStore)          │
 * │                          │                          │
 * │   Messages stream here   │   Highlights overlay     │
 * │   without affecting      │   without being affected │
 * │   the PDF canvas.        │   by token streaming.    │
 * │                          │                          │
 * └──────────────────────────┴──────────────────────────┘
 *
 * The strict Zustand store separation ensures that LLM token streaming
 * (useChatStore) does not trigger PDF canvas re-renders (usePDFStore).
 */

import { useCallback } from "react";
import { Settings, BookOpen } from "lucide-react";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { usePDFStore } from "@/stores/usePDFStore";
import { ChatInterface } from "@/components/Chat/ChatInterface";
import { PDFViewer } from "@/components/PDFViewer/PDFViewer";
import { SettingsPanel } from "@/components/Settings/SettingsPanel";

export default function App() {
  const toggleSettings = useSettingsStore((s) => s.toggleSettingsPanel);
  const currentDocumentPath = usePDFStore((s) => s.currentDocumentPath);

  const handleLogoClick = useCallback(() => {
    usePDFStore.getState().loadDocument("");
  }, []);

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-stone-200 bg-white px-4 py-2.5 shadow-sm z-10">
        <div className="flex items-center gap-2">
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

      {/* Main split-pane layout */}
      <main className="flex flex-1 overflow-hidden">
        {/* Chat pane */}
        <div className="w-[420px] flex-shrink-0 border-r border-stone-200 flex flex-col overflow-hidden">
          <ChatInterface />
        </div>

        {/* PDF viewer pane */}
        <div className="flex-1 overflow-hidden">
          <PDFViewer />
        </div>
      </main>

      {/* Settings overlay panel */}
      <SettingsPanel />
    </div>
  );
}
