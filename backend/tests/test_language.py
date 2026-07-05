"""
Tests for language detection and Sanskrit processing pipeline.
"""

import pytest
from app.core.language.detector import detect_language, has_devanagari, detect_mixed_languages
from app.core.language.sanskrit import (
    build_glossary_for_chunk,
    extract_sanskrit_terms,
    transliterate_devanagari,
    SANSKRIT_GLOSSARY,
)


class TestLanguageDetection:
    """Tests for the language detection module."""

    def test_detect_english(self):
        text = "The divine consciousness manifests in all forms of existence."
        assert detect_language(text) == "en"

    def test_detect_french(self):
        text = "La conscience divine se manifeste dans toutes les formes de l'existence."
        lang = detect_language(text)
        assert lang == "fr", f"Expected 'fr', got '{lang}'"

    def test_detect_devanagari(self):
        text = "सत् चित् आनन्द ब्रह्मन् आत्मन्"
        assert detect_language(text) == "sa"

    def test_devanagari_presence(self):
        assert has_devanagari("सत्") is True
        assert has_devanagari("Sat") is False
        assert has_devanagari("La conscience सत् divine") is True

    def test_detect_mixed_with_devanagari(self):
        text = "The concept of सत् (Sat) is fundamental to Vedanta philosophy."
        langs = detect_mixed_languages(text)
        assert "sa" in langs, "Mixed text with Devanagari should include 'sa'"

    def test_empty_text_defaults_to_english(self):
        assert detect_language("") == "en"
        assert detect_language("   ") == "en"


class TestSanskritProcessing:
    """Tests for Sanskrit transliteration and glossary generation."""

    def test_has_devanagari(self):
        assert has_devanagari("ब्रह्म") is True
        assert has_devanagari("brahman") is False

    def test_transliterate_devanagari_returns_none_for_latin(self):
        result = transliterate_devanagari("brahman yoga")
        assert result is None, "Latin text should return None from transliterator"

    def test_glossary_matches_known_terms(self):
        text = "The yoga of brahman leads to ananda through karma"
        glossary = build_glossary_for_chunk(text)

        assert "yoga" in glossary, "Should detect 'yoga'"
        assert "brahman" in glossary, "Should detect 'brahman'"
        assert "ananda" in glossary, "Should detect 'ananda'"
        assert "karma" in glossary, "Should detect 'karma'"

    def test_glossary_empty_for_non_sanskrit(self):
        text = "The quick brown fox jumps over the lazy dog"
        glossary = build_glossary_for_chunk(text)
        assert len(glossary) == 0, "Non-Sanskrit text should produce empty glossary"

    def test_glossary_all_terms_have_definitions(self):
        """All terms in SANSKRIT_GLOSSARY should have non-empty definitions."""
        for term, definition in SANSKRIT_GLOSSARY.items():
            assert term, "Term should not be empty"
            assert definition, f"Definition for '{term}' should not be empty"
            assert len(definition) > 5, f"Definition for '{term}' is too short: '{definition}'"

    def test_extract_sanskrit_terms_finds_iast(self):
        """IAST marker characters should flag a term as Sanskrit."""
        text = "The ātman is identical with brahman in Advaita"
        terms = extract_sanskrit_terms(text)
        assert any("tman" in t for t in terms), "Should extract IAST-marked terms"
