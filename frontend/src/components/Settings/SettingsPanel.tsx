/**
 * Settings panel: right sidebar for configuring retrieval and LLM parameters.
 *
 * Opens as an overlay panel. Contains:
 * - Similarity alpha slider (dense/sparse blend)
 * - Language toggles (English/French/Sanskrit)
 * - Top-K and graph hop controls
 * - Document filter (select specific PDFs)
 */

import { useEffect } from "react";
import { clsx } from "clsx";
import * as Dialog from "@radix-ui/react-dialog";
import { X, Settings, RotateCcw } from "lucide-react";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { SimilaritySlider } from "./SimilaritySlider";
import { LanguageToggle } from "./LanguageToggle";

export function SettingsPanel() {
  const {
    isSettingsOpen,
    toggleSettingsPanel,
    settings,
    updateSettings,
    resetToDefaults,
    availableDocuments,
  } = useSettingsStore();

  // Load available documents on mount
  useEffect(() => {
    fetch("/api/v1/documents/")
      .then((r) => r.json())
      .then((docs) => useSettingsStore.getState().setAvailableDocuments(docs))
      .catch(console.error);
  }, []);

  return (
    <Dialog.Root open={isSettingsOpen} onOpenChange={toggleSettingsPanel}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30 z-40 animate-fade-in" />
        <Dialog.Content
          className={clsx(
            "fixed right-0 top-0 h-full w-80 bg-white shadow-2xl z-50",
            "flex flex-col animate-slide-up"
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
            <div className="flex items-center gap-2">
              <Settings className="h-4 w-4 text-stone-600" />
              <Dialog.Title className="text-sm font-semibold text-stone-800">
                Retrieval Settings
              </Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <button className="rounded p-1 hover:bg-stone-100" aria-label="Close settings">
                <X className="h-4 w-4 text-stone-500" />
              </button>
            </Dialog.Close>
          </div>

          {/* Scrollable settings content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {/* Similarity slider */}
            <section>
              <SimilaritySlider />
            </section>

            <div className="border-t border-stone-100" />

            {/* Language toggles */}
            <section>
              <LanguageToggle />
            </section>

            <div className="border-t border-stone-100" />

            {/* Top-K control */}
            <section className="space-y-2">
              <label className="text-sm font-medium text-stone-700">
                Results per Query (Top-K)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={1}
                  max={20}
                  value={settings.top_k}
                  onChange={(e) => updateSettings({ top_k: Number(e.target.value) })}
                  className="flex-1 accent-amber-500"
                  aria-label="Top K results"
                />
                <span className="text-sm font-mono text-stone-700 w-6 text-right">
                  {settings.top_k}
                </span>
              </div>
              <p className="text-xs text-stone-500">
                Number of context chunks retrieved for each query.
              </p>
            </section>

            <div className="border-t border-stone-100" />

            {/* Graph hops */}
            <section className="space-y-2">
              <label className="text-sm font-medium text-stone-700">
                Knowledge Graph Depth
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={5}
                  value={settings.graph_hops}
                  onChange={(e) =>
                    updateSettings({ graph_hops: Number(e.target.value) })
                  }
                  className="flex-1 accent-amber-500"
                  aria-label="Graph traversal hops"
                />
                <span className="text-sm font-mono text-stone-700 w-6 text-right">
                  {settings.graph_hops}
                </span>
              </div>
              <p className="text-xs text-stone-500">
                How many hops to traverse the knowledge graph. 0 = disabled.
                Higher values enable multi-hop philosophical reasoning.
              </p>
            </section>

            {/* Document filter */}
            {availableDocuments.length > 0 && (
              <>
                <div className="border-t border-stone-100" />
                <section className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-stone-700">
                      Filter Documents
                    </label>
                    <button
                      onClick={() =>
                        settings.selected_document_ids.length > 0
                          ? useSettingsStore.getState().clearDocumentSelection()
                          : useSettingsStore.getState().selectAllDocuments()
                      }
                      className="text-xs text-amber-600 hover:text-amber-700"
                    >
                      {settings.selected_document_ids.length > 0
                        ? "Clear all"
                        : "Select all"}
                    </button>
                  </div>
                  <p className="text-xs text-stone-500">
                    Leave empty to search all documents.
                  </p>
                  <div className="max-h-40 overflow-y-auto space-y-1">
                    {availableDocuments.map((doc) => (
                      <label
                        key={doc.id}
                        className="flex items-center gap-2 rounded px-2 py-1 hover:bg-stone-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={settings.selected_document_ids.includes(doc.id)}
                          onChange={() =>
                            useSettingsStore.getState().toggleDocument(doc.id)
                          }
                          className="accent-amber-500 rounded"
                        />
                        <span className="text-xs text-stone-700 truncate">
                          {doc.title}
                        </span>
                      </label>
                    ))}
                  </div>
                </section>
              </>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-stone-200 px-4 py-3">
            <button
              onClick={resetToDefaults}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-stone-200 py-2 text-sm text-stone-600 hover:bg-stone-50 transition-all"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset to defaults
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
