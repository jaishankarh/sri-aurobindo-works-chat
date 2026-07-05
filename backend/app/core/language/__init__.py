from .detector import detect_language, detect_mixed_languages, has_devanagari
from .sanskrit import (
    SANSKRIT_GLOSSARY,
    build_glossary_for_chunk,
    extract_sanskrit_terms,
    process_chunk_language,
    transliterate_devanagari,
)

__all__ = [
    "detect_language",
    "detect_mixed_languages",
    "has_devanagari",
    "transliterate_devanagari",
    "extract_sanskrit_terms",
    "build_glossary_for_chunk",
    "process_chunk_language",
    "SANSKRIT_GLOSSARY",
]
