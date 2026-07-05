/**
 * PDF viewer state store (Zustand).
 *
 * Completely decoupled from useChatStore to prevent the heavy PDF canvas
 * from re-rendering when chat tokens stream in. This is the primary
 * performance isolation measure described in the technical spec.
 *
 * Only PDFViewer, HighlightLayer, and CitationCard components subscribe here.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type { Citation, PDFHighlight, PageDimensions, ViewportDimensions } from "@/types";
import { getCitationColor } from "@/utils/coordinates";

interface PDFStore {
  // Current document
  currentDocumentPath: string | null;
  currentPage: number;
  totalPages: number;
  pageDimensions: PageDimensions | null;
  viewportDimensions: ViewportDimensions | null;

  // Highlights
  highlights: PDFHighlight[];
  activeHighlightId: string | null;

  // UI state
  zoom: number;
  isSidebarOpen: boolean;

  // Actions
  loadDocument: (path: string, page?: number) => void;
  setCurrentPage: (page: number) => void;
  setTotalPages: (total: number) => void;
  setPageDimensions: (dims: PageDimensions) => void;
  setViewportDimensions: (dims: ViewportDimensions) => void;
  setHighlights: (citations: Citation[]) => void;
  addHighlights: (citations: Citation[]) => void;
  setActiveHighlight: (id: string | null) => void;
  clearHighlights: () => void;
  jumpToCitation: (citation: Citation) => void;
  setZoom: (zoom: number) => void;
  toggleSidebar: () => void;
}

export const usePDFStore = create<PDFStore>()(
  subscribeWithSelector((set, get) => ({
    currentDocumentPath: null,
    currentPage: 1,
    totalPages: 0,
    pageDimensions: null,
    viewportDimensions: null,
    highlights: [],
    activeHighlightId: null,
    zoom: 1.0,
    isSidebarOpen: true,

    loadDocument: (path, page = 1) =>
      set({
        currentDocumentPath: path,
        currentPage: page,
        totalPages: 0,
        highlights: [],
        activeHighlightId: null,
        pageDimensions: null,
        viewportDimensions: null,
      }),

    setCurrentPage: (page) => set({ currentPage: page }),

    setTotalPages: (total) => set({ totalPages: total }),

    setPageDimensions: (dims) => set({ pageDimensions: dims }),

    setViewportDimensions: (dims) => set({ viewportDimensions: dims }),

    setHighlights: (citations) =>
      set({
        highlights: citations.map((citation, i) => ({
          id: citation.chunk_id,
          citation,
          color: getCitationColor(i, false),
          isActive: false,
        })),
      }),

    addHighlights: (citations) => {
      const existing = get().highlights;
      const existingIds = new Set(existing.map((h) => h.id));
      const newHighlights: PDFHighlight[] = citations
        .filter((c) => !existingIds.has(c.chunk_id))
        .map((citation, i) => ({
          id: citation.chunk_id,
          citation,
          color: getCitationColor(existing.length + i, false),
          isActive: false,
        }));
      set({ highlights: [...existing, ...newHighlights] });
    },

    setActiveHighlight: (id) =>
      set((state) => ({
        activeHighlightId: id,
        highlights: state.highlights.map((h) => ({
          ...h,
          isActive: h.id === id,
          color: getCitationColor(
            state.highlights.findIndex((x) => x.id === h.id),
            h.id === id
          ),
        })),
      })),

    clearHighlights: () =>
      set({ highlights: [], activeHighlightId: null }),

    jumpToCitation: (citation) => {
      const { loadDocument, setCurrentPage, setActiveHighlight } = get();
      if (get().currentDocumentPath !== citation.file_path) {
        loadDocument(citation.file_path, citation.page_number);
      } else {
        setCurrentPage(citation.page_number);
      }
      setActiveHighlight(citation.chunk_id);
    },

    setZoom: (zoom) => set({ zoom: Math.max(0.25, Math.min(4.0, zoom)) }),

    toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  }))
);
