"""
text_editor.py

Applies edits to a working fitz.Document:

- replace_text(): removes an existing text span (via PDF redaction, so
  the original glyphs are actually deleted rather than just painted
  over) and inserts replacement text using the original position,
  font, and color. Font size defaults to the original span's size and
  is preserved unless the caller passes an explicit font_size (from
  the user's manual font-size control) or the text genuinely doesn't
  fit the *available editable area* (see below) with no explicit size
  given.

- add_text(): inserts a brand-new text object at a user-chosen point.

Both operate on a working copy of the document; the caller is
responsible for keeping the original bytes untouched (see
edit_history.py and app.py).

IMPORTANT - background handling:
Redaction here is deliberately configured to remove *only the text
glyphs* inside the target rectangle and to leave every other page
object (vector fills, table/cell shading, images, borders) completely
untouched: fill=None + cross_out=False on the redaction annotation,
and images/graphics set to "none" on apply_redactions(). Whatever was
genuinely behind the text (almost always just the plain page/cell
background) shows through exactly as it already existed, instead of
us guessing and painting an approximate color.

IMPORTANT - available width vs. original bounding box:
The original text's bounding box is only a few points wide for short
strings like "B" - that is where the glyph happened to end, not a
hard container. Treating it as a strict maximum width caused short
replacements like "A+" to be shrunk all the way to the minimum font
size even though there was plenty of visible room in the surrounding
cell.

Instead, `_right_boundary()` looks for the real constraints around the
text - the next text span on the same line, the nearest vertical
table/border line to the right (from the page's vector drawings), or
failing both, the page's right margin - and only that boundary is
used as the width limit. The original font size is then kept as-is
whenever it fits inside that real boundary, which is true for the
overwhelming majority of small edits like "B" -> "A+".
"""
from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF

from . import font_matcher

MIN_FONT_SIZE = 6.0
FONT_STEP = 0.5
BBOX_PADDING = 0.75    # points of extra margin when clearing old text
PAGE_MARGIN = 18.0     # fallback right margin from the page edge, in points
LINE_SAFETY_MARGIN = 2.0  # keep a small gap from a detected border/next span

# Redaction options: touch text only, leave images/vector graphics alone.
# Looked up via getattr with numeric fallbacks so this keeps working across
# PyMuPDF versions where these constants may not all be exported.
_REDACT_IMAGE_NONE = getattr(fitz, "PDF_REDACT_IMAGE_NONE", 0)
_REDACT_LINE_ART_NONE = getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0)


@dataclass
class EditResult:
    success: bool
    warning: str | None = None
    used_font_size: float | None = None


def _clear_area(page: fitz.Page, rect: fitz.Rect) -> None:
    """
    Remove text (and only text) inside `rect` via a real PDF redaction,
    without painting any fill color and without touching images or
    vector graphics that happen to overlap the rectangle.
    """
    page.add_redact_annot(rect, fill=None, cross_out=False)
    page.apply_redactions(
        images=_REDACT_IMAGE_NONE,
        graphics=_REDACT_LINE_ART_NONE,
    )


def _right_boundary(page: fitz.Page, bbox: fitz.Rect) -> float:
    """
    Find the nearest real obstacle to the right of `bbox` on its line:
    another piece of text, a vertical table/border line, or (as a last
    resort) the page's right margin. This - not the original glyphs'
    own tight bounding box - is what should limit the replacement
    text's width.
    """
    y_center = (bbox.y0 + bbox.y1) / 2.0
    candidates: list[float] = []

    # 1) The next text span to the right, on (approximately) the same line.
    try:
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # text blocks only
                continue
            for line in block.get("lines", []):
                lb = line.get("bbox", (0, 0, 0, 0))
                if lb[1] - 1 <= y_center <= lb[3] + 1:
                    for sp in line.get("spans", []):
                        sx0 = sp["bbox"][0]
                        if sx0 > bbox.x1 + 0.5:
                            candidates.append(sx0)
    except Exception:
        pass

    # 2) The nearest vertical table/border line to the right.
    try:
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if rect is None:
                continue
            x0, y0, x1, y1 = rect
            width, height = x1 - x0, y1 - y0
            is_vertical_line_like = width <= 2.5 and height >= 2.0
            if is_vertical_line_like and x0 > bbox.x1 - 0.5:
                if y0 - 2 <= y_center <= y1 + 2:
                    candidates.append(x0)
    except Exception:
        pass

    # 3) Fallback: the page's right margin.
    candidates.append(page.rect.width - PAGE_MARGIN)

    return min(candidates)


def _available_width(page: fitz.Page, bbox: fitz.Rect, origin_x: float) -> float:
    """Usable width in points from the text's start point to the nearest
    real obstacle to the right, minus a small safety margin."""
    boundary = _right_boundary(page, bbox)
    width = boundary - origin_x - LINE_SAFETY_MARGIN
    return max(width, 4.0)  # never collapse to zero/negative


def _fit_font_size(
    text: str, fontname: str, start_size: float, max_width: float
) -> tuple[float, bool]:
    """
    Shrink font size in FONT_STEP increments until the text fits
    max_width, down to MIN_FONT_SIZE. Returns (final_size, fits).
    Only used when the caller has not specified an explicit font size.
    """
    size = start_size
    while size >= MIN_FONT_SIZE:
        width = fitz.get_text_length(text, fontname=fontname, fontsize=size)
        if width <= max_width:
            return size, True
        size -= FONT_STEP
    return MIN_FONT_SIZE, False


def replace_text(
    doc: fitz.Document,
    page_number: int,
    span: dict,
    new_text: str,
    font_size: float | None = None,
) -> EditResult:
    """
    Replace the text described by `span` (as returned by
    text_extractor.extract_page_spans) with `new_text` on the given
    page, preserving position, font, color, and rotation, and leaving
    the true original background fully intact.

    Font size behavior:
      - font_size=None (default): use the original span's font size.
        It is only reduced - and only down to what's needed - if the
        text doesn't fit the real available width around it (see
        _available_width / _right_boundary above). For the vast
        majority of edits (e.g. "B" -> "A+") the original size fits
        comfortably and is kept unchanged.
      - font_size=<number>: an explicit size chosen by the user via
        the manual font-size control. That exact size is always used
        - it is never silently overridden - and a warning is returned
        only if it doesn't fit the available width, so the user can
        decide whether to adjust it.
    """
    page = doc[page_number]
    bbox = fitz.Rect(span["bbox"])
    cover = fitz.Rect(
        bbox.x0 - BBOX_PADDING,
        bbox.y0 - BBOX_PADDING,
        bbox.x1 + BBOX_PADDING,
        bbox.y1 + BBOX_PADDING,
    )

    if new_text.strip() == "":
        # Treat "replace with empty text" as "delete the text" - just
        # clear the original glyphs and leave the real background as-is.
        _clear_area(page, cover)
        return EditResult(success=True, warning=None, used_font_size=0)

    fontname = font_matcher.map_to_base14(span["font"], 0)
    color = font_matcher.hex_to_rgb01(span["color"])
    rotation = span.get("rotation", 0) % 360
    origin_x = span["origin"][0]

    available_width = _available_width(page, bbox, origin_x)

    if font_size is not None:
        # Explicit, user-chosen size - respect it exactly.
        final_size = max(float(font_size), 0.5)
        width = fitz.get_text_length(new_text, fontname=fontname, fontsize=final_size)
        fits = width <= available_width
        warning = None
        if not fits:
            warning = (
                f"At {final_size:g}pt, the replacement text is wider than the "
                "available space around the original text and may overflow "
                "into nearby content. Reduce the font size or shorten the "
                "text if you'd like it to fit cleanly."
            )
    else:
        # No explicit size given - keep the original size whenever it fits
        # the real available area; only shrink as far as truly necessary.
        original_size = span["size"]
        final_size, fits = _fit_font_size(
            new_text, fontname, original_size, available_width
        )
        warning = None
        if not fits:
            warning = (
                "The replacement text is too long to fit the available space "
                f"around it even at the minimum font size ({MIN_FONT_SIZE:g}pt). "
                "It has been inserted at the minimum size but may overflow "
                "into nearby content - please shorten the text or set a "
                "smaller font size."
            )

    # 1) Remove only the original glyphs. Nothing is painted over the
    #    area, so whatever real background existed there remains untouched.
    _clear_area(page, cover)

    # 2) Insert the replacement text at the original baseline origin, so
    #    it sits at exactly the same position as the text it replaced.
    origin = fitz.Point(span["origin"][0], span["origin"][1])
    insert_kwargs = dict(fontname=fontname, fontsize=final_size, color=color)
    if rotation != 0:
        page.insert_text(origin, new_text, rotate=rotation, **insert_kwargs)
    else:
        page.insert_text(origin, new_text, **insert_kwargs)

    return EditResult(success=True, warning=warning, used_font_size=final_size)


def add_text(
    doc: fitz.Document,
    page_number: int,
    x: float,
    y: float,
    text: str,
    fontsize: float = 12.0,
    color_hex: str = "#000000",
    bold: bool = False,
    italic: bool = False,
) -> EditResult:
    """Insert a brand-new text object at PDF point (x, y) (baseline)."""
    if not text.strip():
        return EditResult(success=False, warning="Text cannot be empty.")

    page = doc[page_number]
    fontname = font_matcher.sans_font_for_style(bold, italic)
    color = font_matcher.hex_to_rgb01(color_hex)

    page.insert_text(
        fitz.Point(x, y), text, fontname=fontname, fontsize=fontsize, color=color
    )
    return EditResult(success=True, warning=None, used_font_size=fontsize)
