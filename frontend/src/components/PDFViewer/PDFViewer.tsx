/**
 * PDFViewer component: renders PDF pages using react-pdf (PDF.js) and
 * overlays precise bounding-box highlight layers.
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
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { clsx } from "clsx";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  BookOpen,
} from "lucide-react";
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
  } = usePDFStore();

  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const pageWidth = Math.round(BASE_PAGE_WIDTH * zoom);

  const handleDocumentLoadSuccess = useCallback(
    ({ numPages }: { numPages: number }) => {
      setTotalPages(numPages);
      setIsLoading(false);
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

  if (!currentDocumentPath) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-stone-100 text-stone-400">
        <BookOpen className="h-16 w-16 text-stone-300" />
        <div className="text-center">
          <p className="font-medium text-stone-600">No document selected</p>
          <p className="text-sm mt-1">
            Click a citation in the chat to open the source document
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-stone-100">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-stone-200 bg-white px-3 py-2 text-sm">
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
          {currentDocumentPath.split("/").pop()}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* PDF canvas area */}
        <div className="flex-1 overflow-auto p-4">
          {loadError ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center text-red-600">
                <p className="font-medium">Failed to load PDF</p>
                <p className="text-sm mt-1">{loadError}</p>
              </div>
            </div>
          ) : (
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
                      className="bg-white animate-pulse"
                      style={{ width: pageWidth, height: Math.round(pageWidth * 1.294) }}
                    />
                  }
                />
                {/* Highlight overlay — MUST be inside the Page container */}
                <HighlightLayer currentPage={currentPage} />
              </div>
            </Document>
          )}
        </div>

        {/* Citations sidebar */}
        {activeCitations.length > 0 && (
          <div className="w-64 flex-shrink-0 border-l border-stone-200 bg-white overflow-y-auto p-3">
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
    </div>
  );
}
