/**
 * PDF bounding box coordinate normalization utilities.
 *
 * PDF native coordinates use a bottom-left origin (y=0 at page bottom).
 * Browser canvas / PDF.js uses a top-left origin (y=0 at page top).
 *
 * This module provides the mathematical transformation to convert between
 * these two coordinate systems, with support for arbitrary zoom scales.
 *
 * Algorithm:
 *   scale_x = viewport_width / page_width
 *   scale_y = viewport_height / page_height
 *   canvas_top    = (page_height - pdf_y1) * scale_y
 *   canvas_bottom = (page_height - pdf_y0) * scale_y
 *   canvas_left   = pdf_x0 * scale_x
 *   canvas_right  = pdf_x1 * scale_x
 *
 * Reference: PDF spec ISO 32000-2 §8.3.2; PDF.js viewport.convertToViewportRectangle()
 */

import type { BoundingBox, HighlightRect, PageDimensions, ViewportDimensions } from "@/types";

/**
 * Convert a PDF bounding box (bottom-left origin) to browser canvas coordinates (top-left origin).
 *
 * @param bbox       - PDF native bounding box [x0, y0, x1, y1] in points
 * @param page       - PDF page dimensions in points (from page.getViewport({scale:1}))
 * @param viewport   - Current canvas viewport dimensions in pixels
 * @returns HighlightRect in pixel coordinates, ready for CSS positioning
 */
export function pdfToCanvas(
  bbox: BoundingBox,
  page: PageDimensions,
  viewport: ViewportDimensions
): HighlightRect {
  if (page.width === 0 || page.height === 0) {
    throw new Error("Page dimensions cannot be zero");
  }

  const scaleX = viewport.width / page.width;
  const scaleY = viewport.height / page.height;

  // Invert Y axis: PDF y=0 is at page BOTTOM, canvas y=0 is at page TOP
  const top = (page.height - bbox.y1) * scaleY;
  const bottom = (page.height - bbox.y0) * scaleY;
  const left = bbox.x0 * scaleX;
  const right = bbox.x1 * scaleX;

  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  };
}

/**
 * Scale a highlight rect by an additional zoom factor.
 *
 * Use this when the PDF viewer zoom changes after the initial coordinate calculation.
 */
export function scaleHighlight(rect: HighlightRect, scale: number): HighlightRect {
  return {
    left: rect.left * scale,
    top: rect.top * scale,
    right: rect.right * scale,
    bottom: rect.bottom * scale,
    width: rect.width * scale,
    height: rect.height * scale,
  };
}

/**
 * Convert BoundingBox object to [x0, y0, x1, y1] array (PDF.js format).
 */
export function bboxToArray(bbox: BoundingBox): [number, number, number, number] {
  return [bbox.x0, bbox.y0, bbox.x1, bbox.y1];
}

/**
 * Check if a bounding box is valid (non-zero area, correct coordinate order).
 */
export function isValidBBox(bbox: BoundingBox): boolean {
  return (
    bbox.x1 > bbox.x0 &&
    bbox.y1 > bbox.y0 &&
    bbox.x0 >= 0 &&
    bbox.y0 >= 0
  );
}

/**
 * Merge multiple bounding boxes into one encompassing box.
 * Useful for highlighting multi-line text chunks.
 */
export function mergeBBoxes(bboxes: BoundingBox[]): BoundingBox | null {
  if (bboxes.length === 0) return null;
  const first = bboxes[0];
  return bboxes.reduce(
    (acc, bbox) => ({
      x0: Math.min(acc.x0, bbox.x0),
      y0: Math.min(acc.y0, bbox.y0),
      x1: Math.max(acc.x1, bbox.x1),
      y1: Math.max(acc.y1, bbox.y1),
      page_number: first.page_number,
    }),
    { ...first }
  );
}

/**
 * Generate a CSS color with transparency for highlight overlays.
 * Uses a palette inspired by illuminated manuscripts.
 */
export function getCitationColor(index: number, isActive: boolean): string {
  const palette = [
    "rgba(251, 191, 36,",  // amber
    "rgba(134, 239, 172,", // green
    "rgba(147, 197, 253,", // blue
    "rgba(249, 168, 212,", // pink
    "rgba(196, 181, 253,", // purple
    "rgba(253, 186, 116,", // orange
  ];

  const base = palette[index % palette.length];
  const opacity = isActive ? "0.55)" : "0.30)";
  return base + opacity;
}
