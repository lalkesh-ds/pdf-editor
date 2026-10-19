"""
annotations.py

Handles graphical annotations and objects in PDF pages:
- whiteout / redaction
- highlighting
- shapes (rectangle, circle/ellipse, line, arrow)
- freehand pen drawing
- images and signatures
"""
from __future__ import annotations

import math
from typing import Sequence
import fitz  # PyMuPDF

from . import font_matcher


_REDACT_IMAGE_NONE = getattr(fitz, "PDF_REDACT_IMAGE_NONE", 0)
_REDACT_LINE_ART_NONE = getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0)


def add_whiteout(
    doc: fitz.Document,
    page_num: int,
    rect_coords: Sequence[float],
    fill_hex: str = "#ffffff",
    redact_text: bool = True,
) -> bool:
    """
    Apply whiteout to the given rectangle [x0, y0, x1, y1].
    If redact_text is True, permanently removes all text glyphs underneath.
    Fills the rectangle with fill_hex color.
    """
    if not (0 <= page_num < doc.page_count):
        return False

    page = doc[page_num]
    rect = fitz.Rect(rect_coords)
    fill_rgb = font_matcher.hex_to_rgb01(fill_hex)

    if redact_text:
        page.add_redact_annot(rect, fill=fill_rgb, cross_out=False)
        page.apply_redactions(
            images=_REDACT_IMAGE_NONE,
            graphics=_REDACT_LINE_ART_NONE,
        )
    else:
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=fill_rgb, fill=fill_rgb, width=0)
        shape.commit()

    return True


def add_highlight(
    doc: fitz.Document,
    page_num: int,
    rect_coords: Sequence[float],
    color_hex: str = "#ffe066",
    opacity: float = 0.45,
) -> bool:
    """
    Add a highlight annotation or translucent highlight box over rect [x0, y0, x1, y1].
    """
    if not (0 <= page_num < doc.page_count):
        return False

    page = doc[page_num]
    rect = fitz.Rect(rect_coords)
    color_rgb = font_matcher.hex_to_rgb01(color_hex)

    # Use a translucent shape so it works cleanly over any text or table
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(
        color=None,
        fill=color_rgb,
        fill_opacity=opacity,
        stroke_opacity=0,
    )
    shape.commit()
    return True


def add_shape(
    doc: fitz.Document,
    page_num: int,
    shape_type: str,
    coords: Sequence[float],
    stroke_hex: str = "#000000",
    fill_hex: str | None = None,
    stroke_width: float = 2.0,
    opacity: float = 1.0,
) -> bool:
    """
    Draw vector shapes:
    - 'rect': coords=[x0, y0, x1, y1]
    - 'circle' / 'ellipse': coords=[x0, y0, x1, y1] (bounding box)
    - 'line': coords=[x0, y0, x1, y1] (from p1=(x0,y0) to p2=(x1,y1))
    - 'arrow': coords=[x0, y0, x1, y1] (with arrowhead at p2)
    """
    if not (0 <= page_num < doc.page_count):
        return False

    page = doc[page_num]
    stroke_rgb = font_matcher.hex_to_rgb01(stroke_hex) if stroke_hex else None
    fill_rgb = font_matcher.hex_to_rgb01(fill_hex) if fill_hex else None

    shape = page.new_shape()

    if shape_type == "rect":
        rect = fitz.Rect(coords)
        shape.draw_rect(rect)
        shape.finish(
            color=stroke_rgb,
            fill=fill_rgb,
            width=stroke_width,
            stroke_opacity=opacity,
            fill_opacity=opacity if fill_rgb else 0,
        )

    elif shape_type in ("circle", "ellipse"):
        rect = fitz.Rect(coords)
        shape.draw_oval(rect)
        shape.finish(
            color=stroke_rgb,
            fill=fill_rgb,
            width=stroke_width,
            stroke_opacity=opacity,
            fill_opacity=opacity if fill_rgb else 0,
        )

    elif shape_type == "line":
        p1 = fitz.Point(coords[0], coords[1])
        p2 = fitz.Point(coords[2], coords[3])
        shape.draw_line(p1, p2)
        shape.finish(
            color=stroke_rgb or (0, 0, 0),
            width=stroke_width,
            stroke_opacity=opacity,
        )

    elif shape_type == "arrow":
        p1 = fitz.Point(coords[0], coords[1])
        p2 = fitz.Point(coords[2], coords[3])
        shape.draw_line(p1, p2)
        shape.finish(
            color=stroke_rgb or (0, 0, 0),
            width=stroke_width,
            stroke_opacity=opacity,
        )

        # Arrowhead calculation
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length = math.hypot(dx, dy)
        if length > 3:
            arrow_size = min(max(stroke_width * 5.0, 10.0), 28.0)
            angle = math.atan2(dy, dx)
            arrow_angle = math.pi / 6  # 30 degrees
            x_left = p2.x - arrow_size * math.cos(angle - arrow_angle)
            y_left = p2.y - arrow_size * math.sin(angle - arrow_angle)
            x_right = p2.x - arrow_size * math.cos(angle + arrow_angle)
            y_right = p2.y - arrow_size * math.sin(angle + arrow_angle)

            head_shape = page.new_shape()
            head_shape.draw_polyline([
                p2,
                fitz.Point(x_left, y_left),
                fitz.Point(x_right, y_right),
            ])
            head_shape.finish(
                color=stroke_rgb or (0, 0, 0),
                fill=stroke_rgb or (0, 0, 0),
                closePath=True,
                stroke_opacity=opacity,
                fill_opacity=opacity,
            )
            head_shape.commit()

    shape.commit()
    return True


def add_freehand(
    doc: fitz.Document,
    page_num: int,
    points_list: list[list[float]],  # list of [x, y]
    stroke_hex: str = "#000000",
    stroke_width: float = 2.0,
    opacity: float = 1.0,
) -> bool:
    """Draw freehand lines / pen markings from a sequence of [x, y] coordinates."""
    if not (0 <= page_num < doc.page_count) or len(points_list) < 2:
        return False

    page = doc[page_num]
    stroke_rgb = font_matcher.hex_to_rgb01(stroke_hex)
    fitz_points = [fitz.Point(pt[0], pt[1]) for pt in points_list]

    shape = page.new_shape()
    shape.draw_polyline(fitz_points)
    shape.finish(
        color=stroke_rgb,
        width=stroke_width,
        lineCap=1,  # round cap
        lineJoin=1, # round join
        stroke_opacity=opacity,
    )
    shape.commit()
    return True


def add_image_to_page(
    doc: fitz.Document,
    page_num: int,
    image_bytes: bytes,
    rect_coords: Sequence[float],  # [x0, y0, x1, y1]
) -> bool:
    """Insert an image (PNG, JPEG, etc. with alpha transparency) into the page rect."""
    if not (0 <= page_num < doc.page_count):
        return False

    page = doc[page_num]
    rect = fitz.Rect(rect_coords)
    page.insert_image(rect, stream=image_bytes)
    return True
