"""Dataclasses for parsing pipeline output."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChunkType(str, Enum):
    PROSE = "prose"
    POETRY = "poetry"
    PLAY = "play"
    TABLE = "table"
    HEADING = "heading"
    FOOTNOTE = "footnote"
    CORRESPONDENCE = "correspondence"


class PDFCategory(str, Enum):
    PROSE = "prose"
    POETRY = "poetry"
    PLAY = "play"
    MIXED = "mixed"


@dataclass
class BBox:
    """PDF bounding box with page context."""

    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)


@dataclass
class ParsedChunk:
    """A single parsed text chunk with full spatial metadata."""

    text: str
    page_number: int
    chunk_index: int
    chunk_type: ChunkType = ChunkType.PROSE
    bbox: Optional[BBox] = None
    language_tag: str = "en"
    iast_text: Optional[str] = None
    sanskrit_glossary: dict[str, str] = field(default_factory=dict)
    raw_lines: list[str] = field(default_factory=list)

    def to_schema_dict(self) -> dict:
        return {
            "text": self.text,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "chunk_type": self.chunk_type.value,
            "bbox": self.bbox.to_list() if self.bbox else None,
            "language_tag": self.language_tag,
            "iast_text": self.iast_text,
            "sanskrit_glossary": self.sanskrit_glossary,
        }
