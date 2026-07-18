/**
 * PDFViewer: slide-in overlay panel (Radix Dialog, same pattern as
 * SettingsPanel) that renders PDF pages using react-pdf (PDF.js) with
 * precise bounding-box highlight overlays.
 *
 * Opens when usePDFStore.currentDocumentPath is set (a citation was
 * clicked) and closes back to that null/empty state via the overlay,
 * Escape, or its own close button — matching how SettingsPanel opens
 * and closes.
 *
 * State is sourced exclusively from usePDFStore — never from useChatStore.
 * This prevents LLM token streaming from causing canvas re-renders.
 *
 * Coordinate normalization:
 * Page dimensions are captured from the PDF.js onRenderSuccess callback,
 * which provides the viewport in native PDF points. These are stored in
 * usePDFStore and used by HighlightLayer to compute canvas-space positions.
 */

import { useCallback, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, X } from "lucide-react";
import { usePDFStore } from "@/stores/usePDFStore";
import { HighlightLayer } from "./HighlightLayer";
import { CitationCard } from "./CitationCard";

// Configure PDF.js worker (required for react-pdf v9)
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

const ZOOM_STEP = 0.25;
const BASE_PAGE_WIDTH = 816; // pixels at 1.0x scale (approx 8.5in @ 96dpi)

export function PDFViewer() {
  const {
    currentDocumentPath,
    currentPage,
    totalPages,
    zoom,
    highlights,
    activeHighlightId,
    setCurrentPage,
    setTotalPages,
    setPageDimensions,
    setViewportDimensions,
    setZoom,
    loadDocument,
  } = usePDFStore();

  const [loadError, setLoadError] = useState<string | null>(null);
  const isOpen = Boolean(currentDocumentPath);

  const pageWidth = Math.round(BASE_PAGE_WIDTH * zoom);

  const handleClose = useCallback(() => {
    loadDocument("");
  }, [loadDocument]);

  const handleDocumentLoadSuccess = useCallback(
    ({ numPages }: { numPages: number }) => {
      setTotalPages(numPages);
      setLoadError(null);
    },
    [setTotalPages]
  );

  const handlePageRenderSuccess = useCallback(
    (page: { width: number; height: number; originalWidth: number; originalHeight: number }) => {
      // Store native PDF page dimensions (in points) for coordinate normalization
      setPageDimensions({
        width: page.originalWidth,
        height: page.originalHeight,
      });
      // Store rendered viewport dimensions (in pixels) including zoom
      setViewportDimensions({
        width: page.width,
        height: page.height,
        scale: zoom,
      });
    },
    [setPageDimensions, setViewportDimensions, zoom]
  );

  const handlePrevPage = useCallback(() => {
    if (currentPage > 1) setCurrentPage(currentPage - 1);
  }, [currentPage, setCurrentPage]);

  const handleNextPage = useCallback(() => {
    if (currentPage < totalPages) setCurrentPage(currentPage + 1);
  }, [currentPage, totalPages, setCurrentPage]);

  const handleZoomIn = useCallback(() => setZoom(zoom + ZOOM_STEP), [zoom, setZoom]);
  const handleZoomOut = useCallback(() => setZoom(zoom - ZOOM_STEP), [zoom, setZoom]);

  // Citations for the sidebar
  const activeCitations = highlights.filter(
    (h) => h.citation.page_number === currentPage
  );

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30 z-40 animate-fade-in" />
        <Dialog.Content
          className={clsx(
            "fixed right-0 top-0 h-full w-[70vw] max-w-4xl bg-surface shadow-2xl z-50",
            "flex flex-col animate-slide-up"
          )}
        >
          <Dialog.Title className="sr-only">PDF Viewer</Dialog.Title>
          {/* Toolbar */}
          <div className="flex items-center gap-2 border-b border-stone-200 bg-surface px-3 py-2 text-sm">
            {/* Page navigation */}
            <button
              onClick={handlePrevPage}
              disabled={currentPage <= 1}
              className="p-1 rounded hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-stone-600">
              <span className="font-medium">{currentPage}</span>
              <span className="text-stone-400"> / {totalPages}</span>
            </span>
            <button
              onClick={handleNextPage}
              disabled={currentPage >= totalPages}
              className="p-1 rounded hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </button>

            <div className="mx-2 h-4 w-px bg-stone-200" />

            {/* Zoom controls */}
            <button
              onClick={handleZoomOut}
              disabled={zoom <= 0.25}
              className="p-1 rounded hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Zoom out"
            >
              <ZoomOut className="h-4 w-4" />
            </button>
            <span className="text-stone-600 min-w-[3rem] text-center">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={handleZoomIn}
              disabled={zoom >= 4.0}
              className="p-1 rounded hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Zoom in"
            >
              <ZoomIn className="h-4 w-4" />
            </button>

            {/* Document title */}
            <div className="ml-auto max-w-[200px] truncate text-xs text-stone-500">
              {currentDocumentPath?.split("/").pop()}
            </div>

            <Dialog.Close asChild>
              <button
                className="rounded p-1 hover:bg-stone-100"
                aria-label="Close PDF viewer"
              >
                <X className="h-4 w-4 text-stone-500" />
              </button>
            </Dialog.Close>
          </div>

          <div className="flex flex-1 overflow-hidden bg-stone-100">
            {/* PDF canvas area */}
            <div className="flex-1 overflow-auto p-4">
              {loadError ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center text-red-600">
                    <p className="font-medium">Failed to load PDF</p>
                    <p className="text-sm mt-1">{loadError}</p>
                  </div>
                </div>
              ) : currentDocumentPath ? (
                <Document
                  file={currentDocumentPath}
                  onLoadSuccess={handleDocumentLoadSuccess}
                  onLoadError={(e) => setLoadError(e.message)}
                  loading={
                    <div className="flex items-center justify-center h-64">
                      <div className="animate-pulse text-stone-400">Loading PDF…</div>
                    </div>
                  }
                >
                  <div className="relative inline-block shadow-xl">
                    <Page
                      pageNumber={currentPage}
                      width={pageWidth}
                      onRenderSuccess={handlePageRenderSuccess}
                      renderAnnotationLayer={true}
                      renderTextLayer={true}
                      loading={
                        <div
                          className="bg-surface animate-pulse"
                          style={{ width: pageWidth, height: Math.round(pageWidth * 1.294) }}
                        />
                      }
                    />
                    {/* Highlight overlay — MUST be inside the Page container */}
                    <HighlightLayer currentPage={currentPage} />
                  </div>
                </Document>
              ) : null}
            </div>

            {/* Citations sidebar */}
            {activeCitations.length > 0 && (
              <div className="w-64 flex-shrink-0 border-l border-stone-200 bg-surface overflow-y-auto p-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-500 mb-3">
                  Citations on this page
                </h3>
                <div className="space-y-2">
                  {activeCitations.map((h, i) => (
                    <CitationCard
                      key={h.id}
                      citation={h.citation}
                      index={i}
                      isActive={h.id === activeHighlightId}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
