"""
Unit tests for PDF bounding box coordinate transformations.

PDFs use a bottom-left origin coordinate system while browsers (PDF.js canvas)
use a top-left origin. This module verifies the mathematical correctness of
the coordinate normalization and scaling operations.

Reference: PDF spec (ISO 32000-2), §8.3.2 — User Space
"""

import math
import pytest
from dataclasses import dataclass
from typing import NamedTuple


# ── Coordinate transformation utilities (mirrors frontend utils/coordinates.ts) ──


@dataclass
class PageDimensions:
    """Dimensions of a PDF page in points (1 pt = 1/72 inch)."""
    width: float   # page width in points
    height: float  # page height in points


@dataclass
class ViewportDimensions:
    """Browser canvas viewport dimensions in pixels."""
    width: float   # canvas width in pixels
    height: float  # canvas height in pixels
    scale: float = 1.0  # current zoom scale


@dataclass
class PDFBBox:
    """Bounding box in PDF native coordinates (bottom-left origin)."""
    x0: float
    y0: float
    x1: float
    y1: float

    def width(self) -> float:
        return abs(self.x1 - self.x0)

    def height(self) -> float:
        return abs(self.y1 - self.y0)


@dataclass
class CanvasBBox:
    """Bounding box in browser canvas coordinates (top-left origin, pixels)."""
    left: float
    top: float
    right: float
    bottom: float

    def width(self) -> float:
        return abs(self.right - self.left)

    def height(self) -> float:
        return abs(self.bottom - self.top)


def pdf_to_canvas(
    bbox: PDFBBox,
    page: PageDimensions,
    viewport: ViewportDimensions,
) -> CanvasBBox:
    """
    Transform a PDF bounding box from PDF coordinate space to browser canvas space.

    Algorithm:
    1. Scale factor = viewport.width / page.width (handles zoom)
    2. Invert Y axis: canvas_y = page.height - pdf_y
    3. Apply scale factor to all coordinates

    This is the inverse of what PDF.js viewport.convertToViewportRectangle() does,
    reimplemented in Python for testability.

    Args:
        bbox: Bounding box in PDF points (bottom-left origin)
        page: PDF page dimensions in points
        viewport: Browser canvas dimensions in pixels

    Returns:
        CanvasBBox in pixel coordinates (top-left origin)
    """
    if page.width == 0 or page.height == 0:
        raise ValueError("Page dimensions cannot be zero")

    # Scale factor converts PDF points to canvas pixels
    scale_x = viewport.width / page.width
    scale_y = viewport.height / page.height

    # Invert Y axis (PDF y0 is at bottom, canvas y0 is at top)
    canvas_top = (page.height - bbox.y1) * scale_y
    canvas_bottom = (page.height - bbox.y0) * scale_y
    canvas_left = bbox.x0 * scale_x
    canvas_right = bbox.x1 * scale_x

    return CanvasBBox(
        left=canvas_left,
        top=canvas_top,
        right=canvas_right,
        bottom=canvas_bottom,
    )


def canvas_to_pdf(
    bbox: CanvasBBox,
    page: PageDimensions,
    viewport: ViewportDimensions,
) -> PDFBBox:
    """
    Inverse transform: browser canvas coordinates → PDF coordinate space.

    Used for testing roundtrip accuracy.
    """
    if viewport.width == 0 or viewport.height == 0:
        raise ValueError("Viewport dimensions cannot be zero")

    scale_x = page.width / viewport.width
    scale_y = page.height / viewport.height

    pdf_x0 = bbox.left * scale_x
    pdf_x1 = bbox.right * scale_x
    # Invert Y axis back
    pdf_y0 = page.height - bbox.bottom * scale_y
    pdf_y1 = page.height - bbox.top * scale_y

    return PDFBBox(x0=pdf_x0, y0=pdf_y0, x1=pdf_x1, y1=pdf_y1)


def scale_bbox(bbox: CanvasBBox, scale: float) -> CanvasBBox:
    """Scale a canvas bounding box by the given zoom factor."""
    return CanvasBBox(
        left=bbox.left * scale,
        top=bbox.top * scale,
        right=bbox.right * scale,
        bottom=bbox.bottom * scale,
    )


# ── Test cases ────────────────────────────────────────────────────────────────


class TestYAxisInversion:
    """Tests for the fundamental Y-axis inversion between PDF and canvas space."""

    def test_top_left_corner_maps_correctly(self):
        """A box at the top of the PDF should appear at the top of the canvas."""
        page = PageDimensions(width=612.0, height=792.0)  # US Letter
        viewport = ViewportDimensions(width=612.0, height=792.0)  # 1:1 scale

        # Top of PDF page: y close to page.height (792)
        pdf_bbox = PDFBBox(x0=0, y0=762, x1=200, y1=792)
        canvas_bbox = pdf_to_canvas(pdf_bbox, page, viewport)

        # On canvas, this should be near the TOP (small top value)
        assert canvas_bbox.top >= 0, "Top of page should have non-negative canvas top"
        assert canvas_bbox.top < 40, f"Top of page should be near top of canvas, got {canvas_bbox.top}"
        assert canvas_bbox.bottom > canvas_bbox.top, "Bottom > top in canvas space"

    def test_bottom_left_corner_maps_correctly(self):
        """A box at the bottom of the PDF should appear at the bottom of the canvas."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport = ViewportDimensions(width=612.0, height=792.0)

        # Bottom of PDF page: y close to 0
        pdf_bbox = PDFBBox(x0=0, y0=0, x1=200, y1=30)
        canvas_bbox = pdf_to_canvas(pdf_bbox, page, viewport)

        # On canvas, this should be near the BOTTOM (large top value)
        assert canvas_bbox.top > 750, f"Bottom of page should be near bottom of canvas, got {canvas_bbox.top}"

    def test_center_box_maps_to_center(self):
        """A box at the center of the PDF should map to the center of the canvas."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport = ViewportDimensions(width=612.0, height=792.0)

        # Center of PDF
        center_y = 792 / 2
        pdf_bbox = PDFBBox(x0=200, y0=center_y - 10, x1=400, y1=center_y + 10)
        canvas_bbox = pdf_to_canvas(pdf_bbox, page, viewport)

        canvas_center = (canvas_bbox.top + canvas_bbox.bottom) / 2
        expected_center = 792 / 2  # viewport height / 2

        assert abs(canvas_center - expected_center) < 1.0, (
            f"Center box should map to canvas center. "
            f"Got canvas center={canvas_center}, expected={expected_center}"
        )


class TestScaling:
    """Tests for coordinate scaling when viewport differs from page dimensions."""

    def test_2x_zoom_doubles_pixel_dimensions(self):
        """At 2x zoom, all pixel coordinates should be doubled."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport_1x = ViewportDimensions(width=612.0, height=792.0)
        viewport_2x = ViewportDimensions(width=1224.0, height=1584.0)

        pdf_bbox = PDFBBox(x0=100, y0=100, x1=300, y1=400)

        canvas_1x = pdf_to_canvas(pdf_bbox, page, viewport_1x)
        canvas_2x = pdf_to_canvas(pdf_bbox, page, viewport_2x)

        assert abs(canvas_2x.left - canvas_1x.left * 2) < 0.01, "2x zoom should double left"
        assert abs(canvas_2x.right - canvas_1x.right * 2) < 0.01, "2x zoom should double right"
        assert abs(canvas_2x.width() - canvas_1x.width() * 2) < 0.01, "2x zoom should double width"

    def test_half_zoom_halves_pixel_dimensions(self):
        """At 0.5x zoom, all pixel coordinates should be halved."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport_1x = ViewportDimensions(width=612.0, height=792.0)
        viewport_half = ViewportDimensions(width=306.0, height=396.0)

        pdf_bbox = PDFBBox(x0=100, y0=200, x1=300, y1=400)

        canvas_1x = pdf_to_canvas(pdf_bbox, page, viewport_1x)
        canvas_half = pdf_to_canvas(pdf_bbox, page, viewport_half)

        assert abs(canvas_half.width() - canvas_1x.width() / 2) < 0.01
        assert abs(canvas_half.height() - canvas_1x.height() / 2) < 0.01

    def test_a4_page_scaling(self):
        """Test coordinate scaling for A4 page dimensions (595.28 × 841.89 pt)."""
        page = PageDimensions(width=595.28, height=841.89)
        viewport = ViewportDimensions(width=794.0, height=1123.0)  # ~96 DPI rendering

        scale_x = viewport.width / page.width  # ≈ 1.333
        scale_y = viewport.height / page.height  # ≈ 1.334

        pdf_bbox = PDFBBox(x0=72, y0=72, x1=523, y1=769)  # typical text margins
        canvas = pdf_to_canvas(pdf_bbox, page, viewport)

        expected_left = 72 * scale_x
        assert abs(canvas.left - expected_left) < 0.1, (
            f"Expected left={expected_left:.2f}, got {canvas.left:.2f}"
        )


class TestRoundtrip:
    """Tests that pdf_to_canvas and canvas_to_pdf are exact inverses."""

    @pytest.mark.parametrize("pdf_box", [
        PDFBBox(x0=72, y0=72, x1=540, y1=720),
        PDFBBox(x0=0, y0=0, x1=612, y1=792),
        PDFBBox(x0=100, y0=350, x1=512, y1=442),
        PDFBBox(x0=36, y0=700, x1=576, y1=756),
    ])
    def test_roundtrip_accuracy(self, pdf_box: PDFBBox):
        """Transforming PDF→canvas→PDF should recover original coordinates."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport = ViewportDimensions(width=816.0, height=1056.0)  # 4/3 scale

        canvas = pdf_to_canvas(pdf_box, page, viewport)
        recovered = canvas_to_pdf(canvas, page, viewport)

        assert abs(recovered.x0 - pdf_box.x0) < 0.01, f"x0 mismatch: {recovered.x0} vs {pdf_box.x0}"
        assert abs(recovered.y0 - pdf_box.y0) < 0.01, f"y0 mismatch: {recovered.y0} vs {pdf_box.y0}"
        assert abs(recovered.x1 - pdf_box.x1) < 0.01, f"x1 mismatch: {recovered.x1} vs {pdf_box.x1}"
        assert abs(recovered.y1 - pdf_box.y1) < 0.01, f"y1 mismatch: {recovered.y1} vs {pdf_box.y1}"


class TestEdgeCases:
    """Tests for edge cases and validation."""

    def test_zero_page_width_raises(self):
        """Zero page width should raise ValueError."""
        page = PageDimensions(width=0, height=792.0)
        viewport = ViewportDimensions(width=612.0, height=792.0)
        with pytest.raises(ValueError, match="zero"):
            pdf_to_canvas(PDFBBox(0, 0, 100, 100), page, viewport)

    def test_point_bbox_zero_area(self):
        """A zero-area bounding box should transform to a zero-area canvas box."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport = ViewportDimensions(width=612.0, height=792.0)
        pdf_bbox = PDFBBox(x0=100, y0=100, x1=100, y1=100)
        canvas = pdf_to_canvas(pdf_bbox, page, viewport)
        assert canvas.width() == 0.0
        assert canvas.height() == 0.0

    def test_full_page_bbox(self):
        """A bbox covering the full page should fill the entire canvas."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport = ViewportDimensions(width=816.0, height=1056.0)
        pdf_bbox = PDFBBox(x0=0, y0=0, x1=612, y1=792)
        canvas = pdf_to_canvas(pdf_bbox, page, viewport)

        assert abs(canvas.left) < 0.01
        assert abs(canvas.top) < 0.01
        assert abs(canvas.right - 816.0) < 0.01
        assert abs(canvas.bottom - 1056.0) < 0.01

    def test_x_axis_unchanged(self):
        """X-axis coordinates should scale linearly without inversion."""
        page = PageDimensions(width=612.0, height=792.0)
        viewport = ViewportDimensions(width=612.0, height=792.0)

        # Two boxes at same Y but different X
        left_box = PDFBBox(x0=0, y0=300, x1=100, y1=400)
        right_box = PDFBBox(x0=500, y0=300, x1=612, y1=400)

        left_canvas = pdf_to_canvas(left_box, page, viewport)
        right_canvas = pdf_to_canvas(right_box, page, viewport)

        assert left_canvas.left < right_canvas.left, "Left box should remain left on canvas"
        assert left_canvas.right < right_canvas.right

    def test_scale_bbox_function(self):
        """scale_bbox should multiply all coordinates by the scale factor."""
        canvas = CanvasBBox(left=100, top=200, right=300, bottom=400)
        scaled = scale_bbox(canvas, 2.0)

        assert scaled.left == 200.0
        assert scaled.top == 400.0
        assert scaled.right == 600.0
        assert scaled.bottom == 800.0


class TestHighlightAccuracy:
    """
    Integration tests simulating real-world highlight placement.

    These tests use dimensions from actual Sri Aurobindo corpus PDFs
    (US Letter and A4 formats) to verify highlight accuracy.
    """

    def test_savitri_poetry_line_highlight(self):
        """
        Simulate highlighting a line from Savitri (Book I, Canto I).

        Typical poetry line bounding box from PyMuPDF spatial parser.
        Page: US Letter 8.5×11 in = 612×792 pt
        """
        page = PageDimensions(width=612.0, height=792.0)
        # Simulating a 768px wide canvas at ~1.25x scale
        viewport = ViewportDimensions(width=765.0, height=990.0)

        # A single poetry line approximately 1/3 down the page
        poetry_line_bbox = PDFBBox(x0=144.0, y0=528.0, x1=468.0, y1=544.0)

        canvas = pdf_to_canvas(poetry_line_bbox, page, viewport)

        # Verify the highlight is in the upper third of the canvas (1/3 from top = ~330px)
        canvas_one_third = viewport.height / 3
        assert canvas.top < canvas_one_third + 50, (
            f"Poetry line should be in upper third. top={canvas.top}, threshold={canvas_one_third + 50}"
        )
        # Verify the highlight is not at the very top
        assert canvas.top > 50, "Poetry line should not be at very top of canvas"
        # Verify width is proportional
        assert canvas.width() > 0, "Highlight must have positive width"

    def test_a4_french_text_highlight(self):
        """
        Simulate highlighting French text from The Mother's works.

        Typical A4 page dimensions (595.28 × 841.89 pt).
        """
        page = PageDimensions(width=595.28, height=841.89)
        viewport = ViewportDimensions(width=794.0, height=1123.0)

        # A paragraph block in the middle of an A4 page
        french_para_bbox = PDFBBox(x0=56.7, y0=380.0, x1=538.58, y1=460.0)

        canvas = pdf_to_canvas(french_para_bbox, page, viewport)

        # Should be roughly in the middle of the canvas
        canvas_mid = viewport.height / 2
        bbox_center_y = (canvas.top + canvas.bottom) / 2
        assert abs(bbox_center_y - canvas_mid) < canvas_mid * 0.3, (
            f"Middle-page paragraph should be near canvas center. "
            f"Got {bbox_center_y:.0f}, expected ~{canvas_mid:.0f}"
        )
