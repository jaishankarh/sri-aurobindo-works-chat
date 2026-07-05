import { memo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { clsx } from "clsx";
import { BookOpen, User, Loader2, AlertCircle } from "lucide-react";
import { usePDFStore } from "@/stores/usePDFStore";
import type { ChatMessage, Citation } from "@/types";

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

interface MessageBubbleProps {
  message: ChatMessage;
}

export const MessageBubble = memo(({ message }: MessageBubbleProps) => {
  const { jumpToCitation } = usePDFStore();

  const handleCitationClick = useCallback(
    (citation: Citation) => {
      jumpToCitation(citation);
    },
    [jumpToCitation]
  );

  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const isError = message.status === "error";

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
            : "bg-white border border-stone-200 shadow-sm rounded-tl-sm"
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
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>

            {isStreaming && (
              <span className="inline-flex items-center gap-1 text-amber-600 text-xs mt-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>Generating…</span>
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
