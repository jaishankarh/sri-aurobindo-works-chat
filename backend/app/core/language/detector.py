"""
Language detection and classification for multilingual corpus chunks.

Handles English, French, and Devanagari (Sanskrit) detection.
"""

import re
import unicodedata

# Unicode ranges for Devanagari script
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Sanskrit / Sanskrit-related markers in IAST transliteration
_IAST_MARKERS_RE = re.compile(
    r"[āīūṛṝḷṃḥśṣṭḍṇ]", re.IGNORECASE
)

# French-specific characters and words
_FRENCH_MARKERS_RE = re.compile(
    r"\b(le|la|les|de|du|des|un|une|est|sont|et|en|dans|sur|pour|avec|par|"
    r"que|qui|à|ce|se|lui|leur|leurs|mais|ou|donc|ni|car|je|tu|il|nous|vous|ils)\b",
    re.IGNORECASE,
)
_FRENCH_ACCENT_RE = re.compile(r"[àâäéèêëîïôùûüœç]", re.IGNORECASE)


def detect_language(text: str) -> str:
    """
    Detect the primary language of a text chunk.

    Returns ISO 639-1 code: "en", "fr", or "sa" (Sanskrit/Devanagari).
    Falls back to langdetect for ambiguous cases.
    """
    if not text or not text.strip():
        return "en"

    # Devanagari detection is definitive
    devanagari_chars = len(_DEVANAGARI_RE.findall(text))
    if devanagari_chars > 5:
        return "sa"

    # IAST markers suggest Sanskrit in Latin script
    iast_count = len(_IAST_MARKERS_RE.findall(text))
    if iast_count > 3 and len(text) > 20:
        # Still check if it's primarily French (French has accents but not ṭ ḍ etc.)
        if not _FRENCH_ACCENT_RE.search(text):
            return "sa"

    # French detection
    french_word_count = len(_FRENCH_MARKERS_RE.findall(text))
    word_count = len(text.split())
    if word_count > 5 and french_word_count / max(word_count, 1) > 0.15:
        return "fr"

    if _FRENCH_ACCENT_RE.search(text) and french_word_count > 2:
        return "fr"

    # Use langdetect as fallback for longer texts
    if len(text) > 50:
        try:
            from langdetect import detect, LangDetectException
            lang = detect(text)
            if lang in ("fr", "en", "sa"):
                return lang
            # Map related languages to our supported set
            if lang in ("la",):  # Latin → treat as Sanskrit context
                return "sa"
        except Exception:
            pass

    return "en"


def has_devanagari(text: str) -> bool:
    """Returns True if text contains any Devanagari characters."""
    return bool(_DEVANAGARI_RE.search(text))


def detect_mixed_languages(text: str) -> list[str]:
    """
    Detect all languages present in a multilingual chunk.

    Returns list of detected language codes, ordered by predominance.
    """
    langs = set()
    primary = detect_language(text)
    langs.add(primary)

    # Check for Devanagari alongside Latin text
    if _DEVANAGARI_RE.search(text) and primary != "sa":
        langs.add("sa")

    # Check for French markers alongside English
    if _FRENCH_MARKERS_RE.search(text) and primary != "fr":
        langs.add("fr")

    return [primary] + [l for l in langs if l != primary]
