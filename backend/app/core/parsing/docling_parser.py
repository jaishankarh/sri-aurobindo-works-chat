"""
Docling-based parser for standard prose and structured hierarchical documents.

Docling preserves heading hierarchy, tables, and paragraph semantics,
making it suitable for the essay and philosophical prose works.
"""

import json
import re
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF used for bbox extraction alongside docling

from .models import BBox, ChunkType, ParsedChunk

_HEADING_RE = re.compile(r"^#{1,6}\s+")
_MAX_CHUNK_TOKENS = 512
_APPROX_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return len(text) // _APPROX_CHARS_PER_TOKEN


def _get_page_bbox_map(file_path: str | Path) -> dict[int, list[dict]]:
    """
    Build a map of page_number → list of {text, bbox} using PyMuPDF.

    This allows us to look up spatial coordinates for docling's extracted text.
    """
    doc = fitz.open(str(file_path))
    page_map: dict[int, list[dict]] = {}
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        entries = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = "".join(
                    span["text"] for span in line.get("spans", [])
                ).strip()
                line_bbox = line.get("bbox")
                if line_text and line_bbox:
                    entries.append({"text": line_text, "bbox": list(line_bbox)})
        page_map[page_num + 1] = entries
    doc.close()
    return page_map


def _find_bbox_for_text(
    page_map: dict[int, list[dict]], text: str, page_hint: int | None
) -> tuple[BBox | None, int]:
    """
    Fuzzy match a text snippet to its bounding box in the PDF.

    Returns (BBox, page_number) or (None, -1).
    """
    search_text = text[:80].strip().lower()
    if not search_text:
        return None, -1

    pages_to_search = (
        [page_hint]
        if page_hint and page_hint in page_map
        else sorted(page_map.keys())
    )
    for page_num in pages_to_search:
        entries = page_map.get(page_num, [])
        for entry in entries:
            if search_text[:40] in entry["text"].lower():
                b = entry["bbox"]
                return BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3], page_number=page_num), page_num
    return None, page_hint or 1


def parse_pdf_docling(
    file_path: str | Path,
    max_tokens_per_chunk: int = _MAX_CHUNK_TOKENS,
) -> Iterator[ParsedChunk]:
    """
    Parse a PDF using Docling for prose documents.

    Falls back to PyMuPDF text extraction if Docling is unavailable.
    Yields ParsedChunk objects with spatial bounding boxes.
    """
    try:
        from docling.document_converter import DocumentConverter

        return _parse_with_docling(file_path, max_tokens_per_chunk)
    except ImportError:
        return _parse_with_pymupdf_fallback(file_path, max_tokens_per_chunk)


def _parse_with_docling(
    file_path: str | Path, max_tokens_per_chunk: int
) -> Iterator[ParsedChunk]:
    """Parse using Docling library."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(file_path))
    doc = result.document

    page_map = _get_page_bbox_map(file_path)
    chunk_index = 0

    current_text = ""
    current_page = 1
    current_type = ChunkType.PROSE

    for element, _level in doc.iterate_items():
        element_text = getattr(element, "text", "") or ""
        if not element_text.strip():
            continue

        # Determine chunk type from element label
        label = getattr(element, "label", "text")
        if "heading" in str(label).lower():
            element_type = ChunkType.HEADING
        elif "table" in str(label).lower():
            element_type = ChunkType.TABLE
        else:
            element_type = ChunkType.PROSE

        # Flush current chunk if type changes or size limit reached
        if (
            current_text
            and (
                _estimate_tokens(current_text + element_text) > max_tokens_per_chunk
                or element_type != current_type
            )
        ):
            bbox, page_num = _find_bbox_for_text(page_map, current_text, current_page)
            yield ParsedChunk(
                text=current_text.strip(),
                page_number=page_num,
                chunk_index=chunk_index,
                chunk_type=current_type,
                bbox=bbox,
            )
            chunk_index += 1
            current_text = ""

        current_text = (current_text + " " + element_text).strip()
        current_type = element_type

        try:
            prov = element.prov[0] if element.prov else None
            if prov:
                current_page = getattr(prov, "page_no", current_page) or current_page
        except (AttributeError, IndexError):
            pass

    if current_text.strip():
        bbox, page_num = _find_bbox_for_text(page_map, current_text, current_page)
        yield ParsedChunk(
            text=current_text.strip(),
            page_number=page_num,
            chunk_index=chunk_index,
            chunk_type=current_type,
            bbox=bbox,
        )


def _parse_with_pymupdf_fallback(
    file_path: str | Path, max_tokens_per_chunk: int
) -> Iterator[ParsedChunk]:
    """Fallback parser using PyMuPDF for prose (without whitespace preservation)."""
    doc = fitz.open(str(file_path))
    chunk_index = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        current_text = ""
        block_bboxes: list[list[float]] = []

        for block in blocks:
            if block.get("type") != 0:
                continue

            block_text = ""
            for line in block.get("lines", []):
                line_text = " ".join(
                    span["text"] for span in line.get("spans", [])
                ).strip()
                if line_text:
                    block_text += " " + line_text

            block_text = block_text.strip()
            if not block_text:
                continue

            if _estimate_tokens(current_text + block_text) > max_tokens_per_chunk and current_text:
                x0 = min(b[0] for b in block_bboxes)
                y0 = min(b[1] for b in block_bboxes)
                x1 = max(b[2] for b in block_bboxes)
                y1 = max(b[3] for b in block_bboxes)
                bbox = BBox(x0=x0, y0=y0, x1=x1, y1=y1, page_number=page_num + 1)
                yield ParsedChunk(
                    text=current_text,
                    page_number=page_num + 1,
                    chunk_index=chunk_index,
                    chunk_type=ChunkType.PROSE,
                    bbox=bbox,
                )
                chunk_index += 1
                current_text = block_text
                block_bboxes = [block["bbox"]]
            else:
                current_text = (current_text + " " + block_text).strip()
                block_bboxes.append(block["bbox"])

        if current_text:
            if block_bboxes:
                x0 = min(b[0] for b in block_bboxes)
                y0 = min(b[1] for b in block_bboxes)
                x1 = max(b[2] for b in block_bboxes)
                y1 = max(b[3] for b in block_bboxes)
                bbox = BBox(x0=x0, y0=y0, x1=x1, y1=y1, page_number=page_num + 1)
            else:
                bbox = None
            yield ParsedChunk(
                text=current_text,
                page_number=page_num + 1,
                chunk_index=chunk_index,
                chunk_type=ChunkType.PROSE,
                bbox=bbox,
            )
            chunk_index += 1

    doc.close()
