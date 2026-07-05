/**
 * Shared TypeScript types for the Sri Aurobindo RAG application.
 *
 * These mirror the Pydantic schemas defined in backend/app/models/schemas.py.
 */

// ─────────────────────────── Spatial / Citations ──────────────────────────────

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_number: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  file_path: string;
  page_number: number;
  text_excerpt: string;
  bbox: BoundingBox;
  language_tag: string;
  relevance_score: number;
}

// Normalized highlight for the PDF viewer (browser canvas coordinates)
export interface HighlightRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

// ─────────────────────────── Chat ────────────────────────────────────────────

export type MessageRole = "user" | "assistant";
export type MessageStatus = "complete" | "streaming" | "error";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
  status: MessageStatus;
  created_at: string;
}

// ─────────────────────────── WebSocket ───────────────────────────────────────

export type WSEventType =
  | "token"
  | "citation"
  | "status"
  | "complete"
  | "error";

export interface WSTokenEvent {
  type: "token";
  data: string;
  idx: number;
  session_id: string;
}

export interface WSStatusEvent {
  type: "status";
  data: { status: string; detail?: string };
  session_id: string;
}

export interface WSCitationEvent {
  type: "citation";
  data: { citations: Citation[] };
  session_id: string;
}

export interface WSCompleteEvent {
  type: "complete";
  data: { token_count: number; message_id?: string };
  session_id: string;
}

export interface WSErrorEvent {
  type: "error";
  data: { error: string };
  session_id: string;
}

export type WSEvent =
  | WSTokenEvent
  | WSStatusEvent
  | WSCitationEvent
  | WSCompleteEvent
  | WSErrorEvent;

// ─────────────────────────── Documents ───────────────────────────────────────

export interface Document {
  id: string;
  title: string;
  author?: string;
  language: string;
  category: string;
  file_path: string;
  page_count: number;
  is_processed: boolean;
}

// ─────────────────────────── Settings ────────────────────────────────────────

export interface UserSettings {
  alpha: number;         // 0.0–1.0: dense/sparse balance
  top_k: number;         // number of retrieved chunks
  graph_hops: number;    // graph traversal depth
  language_filter: string[];  // ["en", "fr", "sa"]
  selected_document_ids: string[];
  llm_model: string;
}

// ─────────────────────────── PDF Viewer ──────────────────────────────────────

export interface PDFHighlight {
  id: string;
  citation: Citation;
  color: string;
  isActive: boolean;
}

export interface PageDimensions {
  width: number;
  height: number;
}

export interface ViewportDimensions {
  width: number;
  height: number;
  scale: number;
}

// ─────────────────────────── API Responses ───────────────────────────────────

export interface ApiError {
  detail: string;
  status_code?: number;
}
