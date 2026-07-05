"""
Sanskrit processing: Devanagari → IAST transliteration, Sandhi resolution,
and glossary injection for semantic anchoring.

Pipeline:
1. Detect Devanagari characters
2. Transliterate to IAST using indic-transliteration
3. Attempt Sandhi splitting to isolate root stems
4. Inject English glossary definitions into chunk metadata
"""

import re
from typing import Optional

from .detector import has_devanagari

# IAST special characters for cleanup
_IAST_PUNCT_RE = re.compile(r"[।॥\|]")  # Devanagari dandas

# Common Sanskrit philosophical terms with English glossary
# Expanded programmatically; seeded with high-frequency corpus terms
SANSKRIT_GLOSSARY: dict[str, str] = {
    # Core Aurobindo concepts
    "sat": "pure existence / being",
    "chit": "pure consciousness / awareness",
    "ananda": "bliss / divine delight",
    "brahman": "the ultimate reality / infinite being",
    "atman": "individual self / soul",
    "prakriti": "nature / matter / dynamic energy",
    "purusha": "consciousness / spirit / witness self",
    "maya": "illusion / creative power of brahman",
    "karma": "action and its causal consequences",
    "dharma": "right order / cosmic law / duty",
    "yoga": "union / discipline / path to realization",
    "shakti": "divine energy / power / force",
    "supramental": "beyond-mental consciousness",
    "supermind": "the supramental plane of consciousness",
    "overmind": "the highest mental plane below supermind",
    "integral yoga": "Aurobindo's synthesis of all yoga paths",
    "sadhana": "spiritual practice / discipline",
    "samadhi": "meditative absorption / unity consciousness",
    "nirvana": "liberation / cessation of individual ego",
    "moksha": "liberation from the cycle of rebirth",
    "satchidananda": "existence-consciousness-bliss / the divine trinity",
    "turiya": "the fourth state beyond waking, dreaming, sleep",
    "jivatman": "individual self / embodied soul",
    "paramatman": "supreme self / universal soul",
    "antahkarana": "inner instrument / mind-intellect-ego complex",
    "viveka": "discrimination / discernment between real and unreal",
    "vairagya": "dispassion / non-attachment",
    "sraddha": "faith / trust in the spiritual path",
    "tapas": "austerity / concentrated spiritual energy",
    "ahimsa": "non-violence / harmlessness",
    "satchidananda": "sat-chit-ananda / the triple divine nature",
    "lila": "divine play / cosmic game",
    "kalpa": "cosmic cycle / world-age",
    "rita": "cosmic truth / divine order",
    # The Mother's concepts
    "psychic being": "the soul or divine spark within the individual",
    "psychic fire": "aspiration in the psychic being",
    "supramentalization": "the process of transforming matter by supermind",
}


def transliterate_devanagari(text: str) -> Optional[str]:
    """
    Convert Devanagari script text to IAST (International Alphabet of Sanskrit Transliteration).

    Returns None if no Devanagari characters are present.
    """
    if not has_devanagari(text):
        return None

    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate

        iast = transliterate(text, sanscript.DEVANAGARI, sanscript.IAST)
        # Clean Devanagari punctuation converted to pipe characters
        iast = _IAST_PUNCT_RE.sub(".", iast)
        return iast.strip()
    except ImportError:
        # Fallback: strip Devanagari and signal missing dependency
        return f"[IAST conversion unavailable - install indic-transliteration]: {text}"
    except Exception as e:
        return None


def _simple_sandhi_split(word: str) -> list[str]:
    """
    Heuristic Sandhi splitting for compound IAST words.

    Attempts to split obvious vowel-consonant junctions (external Sandhi).
    This is a simplified approximation; a full morphological analyzer
    (e.g., Sanskrit Heritage API) provides superior results.
    """
    # Common vowel sandhi patterns
    patterns = [
        (r"([aeiouāīūṛ])([aeiouāīūṛ])", r"\1-\2"),  # vowel + vowel
        (r"ā([aeiou])", r"a-a\1"),  # ā + vowel → a + a
        (r"([aeiouāīūṛ])([\w]anta)", r"\1-\2"),  # compound ending in -anta
    ]

    result = word
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)

    return [p.strip("-") for p in result.split("-") if p.strip("-")]


def extract_sanskrit_terms(text: str) -> list[str]:
    """
    Extract Sanskrit terms from IAST-transliterated text.

    Identifies terms by IAST diacritical markers and matches against the glossary.
    """
    iast_word_re = re.compile(
        r"\b\w*[āīūṛṝḷṃḥśṣṭḍṇ]\w*\b", re.IGNORECASE
    )
    terms = iast_word_re.findall(text.lower())
    return list(set(terms))


def build_glossary_for_chunk(text: str, iast_text: Optional[str] = None) -> dict[str, str]:
    """
    Build a Sanskrit glossary dict for a chunk by matching known terms.

    Injects English definitions for detected Sanskrit concepts.
    This anchors Sanskrit embeddings in the multilingual vector space.
    """
    source_text = (iast_text or text).lower()
    glossary: dict[str, str] = {}

    for term, definition in SANSKRIT_GLOSSARY.items():
        term_normalized = term.lower()
        if term_normalized in source_text:
            glossary[term] = definition

    return glossary


def process_chunk_language(
    text: str,
) -> tuple[str, Optional[str], dict[str, str]]:
    """
    Full language processing pipeline for a single chunk.

    Returns:
        (language_tag, iast_text, sanskrit_glossary)
    """
    from .detector import detect_language

    iast_text: Optional[str] = None
    glossary: dict[str, str] = {}

    # Transliterate Devanagari if present
    if has_devanagari(text):
        iast_text = transliterate_devanagari(text)

    lang = detect_language(iast_text or text)

    # Build glossary for Sanskrit content
    if lang == "sa" or iast_text:
        glossary = build_glossary_for_chunk(text, iast_text)

    return lang, iast_text, glossary
