"""
Spatial grid parser using PyMuPDF for poetry, plays, and whitespace-significant layouts.

Uses character-level bounding boxes to reconstruct lines preserving exact
indentation. This is critical for stanzas and dramatic stage directions where
column offset encodes semantic meaning.
"""

import re
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF

from .models import BBox, ChunkType, ParsedChunk

# Poetry heuristics: short lines (<= 80 chars), irregular line lengths
_POETRY_LINE_RATIO_THRESHOLD = 0.4
_MIN_POETRY_LINES = 5
_PLAY_SPEAKER_PATTERN = re.compile(
    r"^([A-Z][A-Z\s\-\.]{1,30})\.\s*$|^([A-Z][A-Z\s\-\.]{1,30}):$"
)


def _is_poetry_block(lines: list[str], page_width: float) -> bool:
    """Heuristic: most lines end before 60% of page width → likely poetry."""
    if len(lines) < _MIN_POETRY_LINES:
        return False
    chars_per_line = [len(l.rstrip()) for l in lines if l.strip()]
    if not chars_per_line:
        return False
    avg_chars = sum(chars_per_line) / len(chars_per_line)
    # Approximate: 6 pts per character at 12pt font on a 612pt wide page
    estimated_avg_width = avg_chars * 6
    return estimated_avg_width < page_width * _POETRY_LINE_RATIO_THRESHOLD


def _is_play_block(lines: list[str]) -> bool:
    """Heuristic: presence of ALL-CAPS speaker labels followed by dialogue."""
    speaker_count = sum(
        1 for l in lines if _PLAY_SPEAKER_PATTERN.match(l.strip())
    )
    return speaker_count >= 2


def _extract_page_spans(page: fitz.Page) -> list[dict]:
    """Extract word-level spans with bounding boxes from a page."""
    blocks = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    spans: list[dict] = []
    for block in blocks:
        if block.get("type") != 0:  # text block only
            continue
        for line in block.get("lines", []):
            line_text = ""
            line_bbox = None
            for span in line.get("spans", []):
                # "rawdict" spans carry per-character entries under "chars"
                # (unlike "dict" mode, which has a flat "text" string directly).
                text = "".join(c.get("c", "") for c in span.get("chars", []))
                bbox = span.get("bbox")
                if text and bbox:
                    line_text += text
                    if line_bbox is None:
                        line_bbox = list(bbox)
                    else:
                        line_bbox[0] = min(line_bbox[0], bbox[0])
                        line_bbox[1] = min(line_bbox[1], bbox[1])
                        line_bbox[2] = max(line_bbox[2], bbox[2])
                        line_bbox[3] = max(line_bbox[3], bbox[3])
            if line_text.strip() and line_bbox:
                spans.append(
                    {
                        "text": line_text,
                        "bbox": line_bbox,
                        "y": (line_bbox[1] + line_bbox[3]) / 2,
                    }
                )
    return spans


def _group_into_stanzas(
    spans: list[dict], gap_threshold: float = 18.0
) -> list[list[dict]]:
    """Group lines into stanzas/paragraphs based on vertical gap."""
    if not spans:
        return []
    spans_sorted = sorted(spans, key=lambda s: s["y"])
    groups: list[list[dict]] = [[spans_sorted[0]]]
    for span in spans_sorted[1:]:
        prev_y = groups[-1][-1]["y"]
        if span["y"] - prev_y > gap_threshold:
            groups.append([])
        groups[-1].append(span)
    return groups


def _spans_to_bbox(spans: list[dict], page_number: int) -> BBox:
    """Compute aggregate bounding box for a list of spans."""
    x0 = min(s["bbox"][0] for s in spans)
    y0 = min(s["bbox"][1] for s in spans)
    x1 = max(s["bbox"][2] for s in spans)
    y1 = max(s["bbox"][3] for s in spans)
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1, page_number=page_number)


def parse_pdf_spatial(
    file_path: str | Path,
    chunk_max_stanzas: int = 6,
) -> Iterator[ParsedChunk]:
    """
    Parse a PDF using spatial grid analysis, preserving whitespace structure.

    Yields ParsedChunk objects with exact bounding boxes for each stanza/block.
    """
    doc = fitz.open(str(file_path))
    global_chunk_index = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_rect = page.rect
        page_width = page_rect.width

        spans = _extract_page_spans(page)
        if not spans:
            continue

        stanzas = _group_into_stanzas(spans)
        page_lines = [s["text"] for group in stanzas for s in group]

        # Determine content type
        is_poetry = _is_poetry_block(page_lines, page_width)
        is_play = _is_play_block(page_lines)

        if is_play:
            chunk_type = ChunkType.PLAY
        elif is_poetry:
            chunk_type = ChunkType.POETRY
        else:
            chunk_type = ChunkType.PROSE

        # Group stanzas into chunks
        current_stanza_group: list[list[dict]] = []
        for stanza in stanzas:
            current_stanza_group.append(stanza)
            if len(current_stanza_group) >= chunk_max_stanzas:
                flat_spans = [s for g in current_stanza_group for s in g]
                raw_lines = [s["text"] for s in flat_spans]
                text = "\n".join(raw_lines)
                bbox = _spans_to_bbox(flat_spans, page_num + 1)
                yield ParsedChunk(
                    text=text,
                    page_number=page_num + 1,
                    chunk_index=global_chunk_index,
                    chunk_type=chunk_type,
                    bbox=bbox,
                    raw_lines=raw_lines,
                )
                global_chunk_index += 1
                current_stanza_group = []

        # Flush remaining stanzas
        if current_stanza_group:
            flat_spans = [s for g in current_stanza_group for s in g]
            raw_lines = [s["text"] for s in flat_spans]
            text = "\n".join(raw_lines)
            if text.strip():
                bbox = _spans_to_bbox(flat_spans, page_num + 1)
                yield ParsedChunk(
                    text=text,
                    page_number=page_num + 1,
                    chunk_index=global_chunk_index,
                    chunk_type=chunk_type,
                    bbox=bbox,
                    raw_lines=raw_lines,
                )
                global_chunk_index += 1

    doc.close()
