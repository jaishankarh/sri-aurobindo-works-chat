/**
 * Language toggle for filtering retrieval by language.
 *
 * The bge-m3 model maps English, French, and Sanskrit into a shared
 * vector space, enabling cross-lingual retrieval. This toggle controls
 * which languages are included in the result set.
 */

import { useCallback } from "react";
import * as Switch from "@radix-ui/react-switch";
import { useSettingsStore } from "@/stores/useSettingsStore";

interface Language {
  code: string;
  label: string;
  description: string;
  flag: string;
}

const LANGUAGES: Language[] = [
  {
    code: "en",
    label: "English",
    description: "Sri Aurobindo's prose, poetry, and Savitri",
    flag: "🇬🇧",
  },
  {
    code: "fr",
    label: "French",
    description: "The Mother's Agenda and Collected Works",
    flag: "🇫🇷",
  },
  {
    code: "sa",
    label: "Sanskrit",
    description: "Vedic terms and IAST transliterations",
    flag: "🕉️",
  },
];

export function LanguageToggle() {
  const { language_filter } = useSettingsStore((state) => state.settings);
  const toggleLanguage = useSettingsStore((state) => state.toggleLanguage);

  const handleToggle = useCallback(
    (code: string) => () => toggleLanguage(code),
    [toggleLanguage]
  );

  return (
    <div className="space-y-3">
      <label className="text-sm font-medium text-stone-700">
        Retrieval Languages
      </label>
      <p className="text-xs text-stone-500">
        bge-m3 maps all languages into the same semantic space, enabling
        cross-lingual retrieval. Toggle to filter source documents by language.
      </p>

      <div className="space-y-2">
        {LANGUAGES.map((lang) => {
          const isEnabled = language_filter.includes(lang.code);
          const isOnlyOne = language_filter.length === 1 && isEnabled;

          return (
            <div
              key={lang.code}
              className="flex items-center justify-between rounded-lg border border-stone-200 bg-stone-50 px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-lg">{lang.flag}</span>
                <div>
                  <p className="text-sm font-medium text-stone-700">
                    {lang.label}
                  </p>
                  <p className="text-xs text-stone-400">{lang.description}</p>
                </div>
              </div>
              <Switch.Root
                checked={isEnabled}
                onCheckedChange={handleToggle(lang.code)}
                disabled={isOnlyOne}
                aria-label={`Toggle ${lang.label} retrieval`}
                className="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent bg-stone-300 transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 data-[state=checked]:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Switch.Thumb className="pointer-events-none inline-block h-5 w-5 translate-x-0 rounded-full bg-white shadow ring-0 transition-transform data-[state=checked]:translate-x-5" />
              </Switch.Root>
            </div>
          );
        })}
      </div>
    </div>
  );
}
