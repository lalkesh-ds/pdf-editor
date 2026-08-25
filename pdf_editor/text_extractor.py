"""
text_extractor.py

Extracts editable text spans (with position, font, size, color,
bold/italic, rotation) from a PDF page using PyMuPDF's detailed
"rawdict"/"dict" text extraction.

A "span" is the smallest unit of text PyMuPDF reports that shares one
consistent font/size/color - this is what the UI lets the user click
and edit.
"""
from __future__ import annotations

import fitz  # PyMuPDF

from . import font_matcher


def extract_page_spans(page: fitz.Page) -> list[dict]:
    """
    Return a list of editable span dicts for a page:

    {
        "id": "b0-l0-s0",
        "text": "Hello World",
        "bbox": [x0, y0, x1, y1],       # PDF points, top-left origin
        "origin": [x, y],               # baseline start point
        "font": "Calibri-Bold",
        "size": 11.0,
        "color": "#111111",
        "bold": True,
        "italic": False,
        "rotation": 0,
    }
    """
    page_dict = page.get_text("dict")
    spans: list[dict] = []

    for b_idx, block in enumerate(page_dict.get("blocks", [])):
        if block.get("type") != 0:  # 0 = text block, 1 = image block
            continue
        for l_idx, line in enumerate(block.get("lines", [])):
            # Approximate line rotation from its writing direction vector.
            dx, dy = line.get("dir", (1.0, 0.0))
            rotation = _direction_to_degrees(dx, dy)

            for s_idx, span in enumerate(line.get("spans", [])):
                text = span.get("text", "")
                if not text.strip():
                    continue

                fontname = span.get("font", "")
                flags = span.get("flags", 0)
                is_bold, is_italic = font_matcher.detect_bold_italic(
                    fontname, flags
                )
                r, g, b = font_matcher.color_int_to_rgb01(
                    span.get("color", 0)
                )

                spans.append(
                    {
                        "id": f"b{b_idx}-l{l_idx}-s{s_idx}",
                        "text": text,
                        "bbox": [round(v, 2) for v in span["bbox"]],
                        "origin": [round(v, 2) for v in span.get(
                            "origin", (span["bbox"][0], span["bbox"][3])
                        )],
                        "font": fontname,
                        "size": round(span.get("size", 11.0), 2),
                        "color": "#{:02x}{:02x}{:02x}".format(
                            round(r * 255), round(g * 255), round(b * 255)
                        ),
                        "bold": is_bold,
                        "italic": is_italic,
                        "rotation": rotation,
                    }
                )
    return spans


def _direction_to_degrees(dx: float, dy: float) -> int:
    """Snap a text-line direction vector to the nearest 0/90/180/270."""
    import math

    angle = math.degrees(math.atan2(-dy, dx))  # PDF y grows downward
    angle = angle % 360
    snapped = round(angle / 90.0) * 90 % 360
    return int(snapped)


def find_span_by_id(page: fitz.Page, span_id: str) -> dict | None:
    """Re-extract spans and locate the one matching span_id."""
    for span in extract_page_spans(page):
        if span["id"] == span_id:
            return span
    return None
