/**
 * CitationCard shows the details of a selected citation in the PDF sidebar.
 *
 * Displays the document title, page, language, text excerpt, and a
 * "Jump to source" button that loads the PDF and scrolls to the highlight.
 */

import { memo, useCallback } from "react";
import { clsx } from "clsx";
import { BookOpen, ChevronRight, Languages } from "lucide-react";
import { usePDFStore } from "@/stores/usePDFStore";
import type { Citation } from "@/types";

const LANGUAGE_LABELS: Record<string, string> = {
  en: "English",
  fr: "French",
  sa: "Sanskrit",
};

interface CitationCardProps {
  citation: Citation;
  index: number;
  isActive: boolean;
}

export const CitationCard = memo(({ citation, index, isActive }: CitationCardProps) => {
  const { jumpToCitation } = usePDFStore();

  const handleJump = useCallback(() => {
    jumpToCitation(citation);
  }, [citation, jumpToCitation]);

  return (
    <div
      className={clsx(
        "rounded-lg border p-3 text-sm transition-all cursor-pointer group",
        isActive
          ? "border-amber-400 bg-amber-50 shadow-sm"
          : "border-stone-200 bg-white hover:border-amber-200 hover:bg-amber-50/50"
      )}
      onClick={handleJump}
    >
      {/* Header: index + title */}
      <div className="flex items-start gap-2">
        <span
          className={clsx(
            "flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-xs font-bold",
            isActive ? "bg-amber-500 text-white" : "bg-stone-200 text-stone-600"
          )}
        >
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-stone-800 truncate leading-tight">
            {citation.document_title}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-stone-500">Page {citation.page_number}</span>
            {citation.language_tag && (
              <>
                <span className="text-stone-300">·</span>
                <span className="inline-flex items-center gap-0.5 text-xs text-stone-500">
                  <Languages className="h-3 w-3" />
                  {LANGUAGE_LABELS[citation.language_tag] || citation.language_tag.toUpperCase()}
                </span>
              </>
            )}
            <span className="text-stone-300">·</span>
            <span className="text-xs text-emerald-600 font-medium">
              {Math.round(citation.relevance_score * 100)}% match
            </span>
          </div>
        </div>
      </div>

      {/* Text excerpt */}
      <p className="mt-2 text-xs text-stone-600 leading-relaxed line-clamp-3 italic">
        "{citation.text_excerpt}"
      </p>

      {/* Jump action */}
      <button
        className={clsx(
          "mt-2 flex items-center gap-1 text-xs font-medium transition-colors",
          isActive
            ? "text-amber-700"
            : "text-stone-400 group-hover:text-amber-600"
        )}
      >
        <BookOpen className="h-3 w-3" />
        <span>Jump to source</span>
        <ChevronRight className="h-3 w-3" />
      </button>
    </div>
  );
});

CitationCard.displayName = "CitationCard";
