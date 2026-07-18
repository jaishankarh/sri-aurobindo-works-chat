import { memo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { clsx } from "clsx";
import { BookOpen, User, Loader2, AlertCircle } from "lucide-react";
import { usePDFStore } from "@/stores/usePDFStore";
import { useChatStore } from "@/stores/useChatStore";
import type { ChatMessage, Citation } from "@/types";

// Friendly labels for each phase of the agentic pipeline (see
// backend prefect_flows.py's publish_event calls). Falls back to the
// backend-provided detail string for a status not listed here, so a new
// backend status still shows something reasonable without a frontend change.
const STATUS_LABELS: Record<string, string> = {
  thinking: "Understanding your question…",
  planning: "Understanding your question…",
  retrieving: "Searching the corpus…",
  selecting_sources: "Reviewing relevant passages…",
  generating: "Writing your answer…",
};

interface CitationBadgeProps {
  citation: Citation;
  index: number;
  onClick: (citation: Citation) => void;
}

const CitationBadge = memo(({ citation, index, onClick }: CitationBadgeProps) => (
  <button
    onClick={() => onClick(citation)}
    className={clsx(
      "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
      "border-amber-300 bg-amber-50 text-amber-800",
      "hover:bg-amber-100 hover:border-amber-400 active:scale-95 transition-all",
      "cursor-pointer"
    )}
    title={`${citation.document_title} — Page ${citation.page_number}`}
  >
    <BookOpen className="h-3 w-3" />
    <span>{index + 1}</span>
  </button>
));

CitationBadge.displayName = "CitationBadge";

// The LLM embeds raw [CITATION:chunk_id] markers in its response text (see
// backend rag_prompt.py). Converting them to markdown link syntax lets a
// single ReactMarkdown pass render them inline exactly where the model
// placed them, via the custom `a` renderer below — rather than either
// showing the raw bracket text or splitting the markdown into multiple
// disjoint block-level chunks.
//
// Using a "#"-fragment rather than a fake protocol (e.g. "citation:") is
// deliberate: react-markdown's default urlTransform sanitizes any URL whose
// scheme isn't in a small allowlist (http(s), ircs?, mailto, xmpp) down to an
// empty string — it silently ate "citation:" links entirely. A fragment has
// no colon before it, so it's treated as relative/safe and passed through
// unchanged; chunk_ids are plain UUIDs (hyphens only, no colons) so this is safe.
// Tolerate a space after the colon, and multiple comma-separated chunk_ids
// in one marker — Gemini doesn't always follow the system prompt's exact
// [CITATION:chunk_id] (single id, no space) format; it sometimes emits
// [CITATION: id1, id2] to back one claim with several sources. The
// backend's extraction regex (rag_prompt.py) has the same allowances.
const CITATION_MARKER_RE = /\[CITATION:\s*([a-f0-9-]{36}(?:\s*,\s*[a-f0-9-]{36})*)\]/g;
const CITATION_LINK_PREFIX = "#cite-";

function citationsToMarkdownLinks(content: string): string {
  return content.replace(CITATION_MARKER_RE, (_match, idsGroup: string) =>
    idsGroup
      .split(",")
      .map((chunkId) => `[cite](${CITATION_LINK_PREFIX}${chunkId.trim()})`)
      .join("")
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export const MessageBubble = memo(({ message }: MessageBubbleProps) => {
  const { jumpToCitation } = usePDFStore();
  const streamingMessageId = useChatStore((s) => s.streamingMessageId);
  const streamingStatus = useChatStore((s) => s.streamingStatus);
  const streamingStatusDetail = useChatStore((s) => s.streamingStatusDetail);

  const handleCitationClick = useCallback(
    (citation: Citation) => {
      jumpToCitation(citation);
    },
    [jumpToCitation]
  );

  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const isError = message.status === "error";

  // streamingStatus is store-global (there's only ever one message
  // streaming at a time), so only the message it actually belongs to should
  // render it — otherwise every "streaming"-status bubble would show it.
  const statusLabel =
    isStreaming && message.id === streamingMessageId && streamingStatus
      ? STATUS_LABELS[streamingStatus] ?? streamingStatusDetail ?? "Generating…"
      : null;

  return (
    <div
      className={clsx(
        "flex gap-3 px-4 py-3 animate-slide-up",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-white",
          isUser ? "bg-stone-600" : "bg-amber-600"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <span className="text-xs font-bold">✦</span>
        )}
      </div>

      {/* Message content */}
      <div
        className={clsx(
          "max-w-[85%] rounded-2xl px-4 py-3",
          isUser
            ? "bg-stone-700 text-white rounded-tr-sm"
            : isError
            ? "bg-red-50 border border-red-200 rounded-tl-sm"
            : "bg-surface border border-stone-200 shadow-sm rounded-tl-sm"
        )}
      >
        {isError ? (
          <div className="flex items-center gap-2 text-red-700 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{message.content || "An error occurred during generation."}</span>
          </div>
        ) : (
          <>
            <div
              className={clsx(
                "prose prose-sm max-w-none",
                isUser
                  ? "prose-invert"
                  : "prose-stone prose-headings:font-serif"
              )}
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children, ...props }) => {
                    if (href?.startsWith(CITATION_LINK_PREFIX)) {
                      const chunkId = href.slice(CITATION_LINK_PREFIX.length);
                      const index = message.citations.findIndex(
                        (c) => c.chunk_id === chunkId
                      );
                      // Citation not resolved yet (e.g. the marker streamed
                      // in before the "citation" event arrived) — drop it
                      // silently rather than showing a raw/broken link; it
                      // reappears once message.citations updates.
                      if (index === -1) return null;
                      return (
                        <CitationBadge
                          citation={message.citations[index]}
                          index={index}
                          onClick={handleCitationClick}
                        />
                      );
                    }
                    return (
                      <a href={href} {...props}>
                        {children}
                      </a>
                    );
                  },
                }}
              >
                {citationsToMarkdownLinks(message.content)}
              </ReactMarkdown>
            </div>

            {statusLabel && (
              <span className="inline-flex items-center gap-1 text-amber-600 text-xs mt-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>{statusLabel}</span>
              </span>
            )}

            {/* Citations */}
            {!isUser && message.citations.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5 border-t border-stone-100 pt-2">
                <span className="text-xs text-stone-400 mr-1">Sources:</span>
                {message.citations.map((citation, i) => (
                  <CitationBadge
                    key={citation.chunk_id}
                    citation={citation}
                    index={i}
                    onClick={handleCitationClick}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
});

MessageBubble.displayName = "MessageBubble";
