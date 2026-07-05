/**
 * Similarity coefficient slider for the alpha (α) parameter.
 *
 * α = 1.0 → Pure dense semantic search (bge-m3 cosine similarity)
 * α = 0.0 → Pure BM25 sparse keyword matching
 * α = 0.5 → Balanced hybrid retrieval via RRF
 */

import { useCallback } from "react";
import * as Slider from "@radix-ui/react-slider";
import { useSettingsStore } from "@/stores/useSettingsStore";

export function SimilaritySlider() {
  const alpha = useSettingsStore((state) => state.settings.alpha);
  const setAlpha = useSettingsStore((state) => state.setAlpha);

  const handleChange = useCallback(
    ([value]: number[]) => setAlpha(value),
    [setAlpha]
  );

  const label =
    alpha >= 0.85
      ? "Pure Semantic"
      : alpha >= 0.6
      ? "Hybrid (semantic-biased)"
      : alpha >= 0.4
      ? "Balanced Hybrid"
      : alpha >= 0.15
      ? "Hybrid (keyword-biased)"
      : "Pure Keyword";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-stone-700">
          Retrieval Mode
        </label>
        <span className="text-xs text-amber-700 font-medium bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
          {label}
        </span>
      </div>

      <Slider.Root
        className="relative flex h-5 items-center select-none touch-none w-full"
        value={[alpha]}
        onValueChange={handleChange}
        min={0}
        max={1}
        step={0.05}
        aria-label="Similarity coefficient alpha"
      >
        <Slider.Track className="relative h-2 flex-1 rounded-full bg-stone-200">
          <Slider.Range className="absolute h-full rounded-full bg-amber-400" />
        </Slider.Track>
        <Slider.Thumb
          className="block h-5 w-5 rounded-full border-2 border-amber-500 bg-white shadow-md focus:outline-none focus:ring-2 focus:ring-amber-300 hover:border-amber-600 cursor-grab active:cursor-grabbing"
          aria-label="Alpha"
        />
      </Slider.Root>

      <div className="flex justify-between text-xs text-stone-400">
        <span>Keyword (α=0)</span>
        <span className="font-mono text-stone-600">α={alpha.toFixed(2)}</span>
        <span>Semantic (α=1)</span>
      </div>

      <p className="text-xs text-stone-500 leading-relaxed">
        Controls the blend between dense vector search and BM25 keyword matching.
        Use higher values for conceptual queries, lower for exact term lookup.
      </p>
    </div>
  );
}
