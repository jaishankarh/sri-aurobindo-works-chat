/**
 * HighlightLayer renders bounding-box highlight overlays on the PDF canvas.
 *
 * Coordinate transformation:
 * PDF native coords (bottom-left origin) → Browser canvas coords (top-left origin)
 * using the pdfToCanvas() utility from utils/coordinates.ts.
 *
 * Each highlight is absolutely positioned over the PDF canvas using CSS.
 * The layer is pointer-events-none by default; individual highlights
 * re-enable pointer events so they can be clicked to activate.
 */

import { memo, useCallback } from "react";
import { usePDFStore } from "@/stores/usePDFStore";
import { pdfToCanvas, isValidBBox } from "@/utils/coordinates";
import type { PDFHighlight, PageDimensions, ViewportDimensions } from "@/types";

interface HighlightItemProps {
  highlight: PDFHighlight;
  page: PageDimensions;
  viewport: ViewportDimensions;
  onActivate: (id: string) => void;
}

const HighlightItem = memo(
  ({ highlight, page, viewport, onActivate }: HighlightItemProps) => {
    const { citation, color, isActive } = highlight;
    const bbox = citation.bbox;

    if (!isValidBBox(bbox)) return null;

    const rect = pdfToCanvas(bbox, page, viewport);

    return (
      <div
        className="absolute cursor-pointer transition-all duration-150"
        style={{
          left: `${rect.left}px`,
          top: `${rect.top}px`,
          width: `${rect.width}px`,
          height: `${rect.height}px`,
          backgroundColor: color,
          border: isActive
            ? "2px solid rgb(217, 119, 6)"
            : "1px solid rgba(0,0,0,0.1)",
          borderRadius: "2px",
          pointerEvents: "auto",
          zIndex: isActive ? 10 : 5,
          boxShadow: isActive
            ? "0 0 0 2px rgba(245, 158, 11, 0.4)"
            : "none",
        }}
        onClick={() => onActivate(highlight.id)}
        title={`${citation.document_title} — Page ${citation.page_number}\n${citation.text_excerpt.slice(0, 100)}…`}
        role="button"
        aria-label={`Citation from ${citation.document_title}, page ${citation.page_number}`}
      />
    );
  }
);

HighlightItem.displayName = "HighlightItem";

interface HighlightLayerProps {
  currentPage: number;
}

export const HighlightLayer = memo(({ currentPage }: HighlightLayerProps) => {
  const { highlights, pageDimensions, viewportDimensions, setActiveHighlight } =
    usePDFStore();

  const handleActivate = useCallback(
    (id: string) => {
      setActiveHighlight(id);
    },
    [setActiveHighlight]
  );

  if (!pageDimensions || !viewportDimensions) return null;

  // Only render highlights on the current page
  const pageHighlights = highlights.filter(
    (h) => h.citation.bbox.page_number === currentPage
  );

  if (pageHighlights.length === 0) return null;

  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 5 }}
      aria-hidden="false"
      role="region"
      aria-label="Citation highlights"
    >
      {pageHighlights.map((highlight) => (
        <HighlightItem
          key={highlight.id}
          highlight={highlight}
          page={pageDimensions}
          viewport={viewportDimensions}
          onActivate={handleActivate}
        />
      ))}
    </div>
  );
});

HighlightLayer.displayName = "HighlightLayer";
