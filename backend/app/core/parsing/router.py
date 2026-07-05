"""
PDF classification router.

Determines whether a PDF should be parsed with the spatial PyMuPDF parser
(poetry, plays) or the Docling hierarchical parser (prose), then dispatches
to the appropriate parser and applies multilingual post-processing.
"""

import re
from pathlib import Path
from typing import Iterator

import fitz

from .docling_parser import parse_pdf_docling
from .models import ChunkType, ParsedChunk, PDFCategory
from .spatial_parser import parse_pdf_spatial

_PLAY_INDICATORS = [
    r"\bACT\s+[IVX]+\b",
    r"\bSCENE\s+[IVX\d]+\b",
    r"\b(Enter|Exit|Exeunt)\b",
    r"^([A-Z]{2,}\s*)+\.\s*$",
]
_PLAY_RE = re.compile("|".join(_PLAY_INDICATORS), re.MULTILINE)

_POETRY_SHORT_LINE_RATIO = 0.45
_POETRY_MIN_SAMPLE_LINES = 20


def _sample_text(file_path: str | Path, max_pages: int = 5) -> str:
    """Extract text from the first N pages for classification."""
    doc = fitz.open(str(file_path))
    sample = ""
    for i in range(min(max_pages, len(doc))):
        sample += doc[i].get_text()
    doc.close()
    return sample


def _classify_pdf(file_path: str | Path) -> PDFCategory:
    """
    Classify a PDF into one of: prose, poetry, play, mixed.

    Uses heuristics on a sample of the document text.
    """
    sample = _sample_text(file_path)
    lines = [l for l in sample.split("\n") if l.strip()]

    if not lines:
        return PDFCategory.PROSE

    # Play detection
    if _PLAY_RE.search(sample):
        return PDFCategory.PLAY

    # Poetry detection: high proportion of short lines
    if len(lines) >= _POETRY_MIN_SAMPLE_LINES:
        doc = fitz.open(str(file_path))
        try:
            page = doc[0]
            page_width = page.rect.width
            doc.close()
        except Exception:
            page_width = 612.0  # letter width default

        avg_chars = sum(len(l) for l in lines) / len(lines)
        estimated_width = avg_chars * 6  # rough char width in points
        if estimated_width < page_width * _POETRY_SHORT_LINE_RATIO:
            return PDFCategory.POETRY

    return PDFCategory.PROSE


def classify_and_parse(
    file_path: str | Path,
    force_category: PDFCategory | None = None,
) -> Iterator[ParsedChunk]:
    """
    Main entry point: classify a PDF and dispatch to the correct parser.

    Args:
        file_path: Path to the PDF file.
        force_category: Override auto-classification if provided.

    Yields:
        ParsedChunk objects from the selected parser.
    """
    category = force_category or _classify_pdf(file_path)

    if category in (PDFCategory.POETRY, PDFCategory.PLAY):
        yield from parse_pdf_spatial(file_path)
    else:
        yield from parse_pdf_docling(file_path)
