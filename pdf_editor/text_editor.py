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
    font_family: str | None = None,
    color_hex: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    x: float | None = None,
    y: float | None = None,
    align: str | None = None,
) -> EditResult:
    """
    Replace the text described by `span` with `new_text` on the given
    page, preserving original font size and style by default, while supporting
    repositioning (x, y) and alignment (left, center, right).
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
        # Treat "replace with empty text" as "delete the text"
        _clear_area(page, cover)
        return EditResult(success=True, warning=None, used_font_size=0)

    # 1. Font Style: Preserve exact original bold/italic unless overridden
    use_bold = bold if bold is not None else span.get("bold", False)
    use_italic = italic if italic is not None else span.get("italic", False)

    # 2. Font Family: Match original font family unless overridden
    if font_family:
        fontname = font_matcher.font_for_family_and_style(font_family, use_bold, use_italic)
    else:
        clean = font_matcher.strip_subset_prefix(span.get("font", ""))
        is_serif = bool(font_matcher._SERIF_HINTS.search(clean))
        is_mono = bool(font_matcher._MONO_HINTS.search(clean))
        fam = "serif" if is_serif else ("mono" if is_mono else "sans")
        fontname = font_matcher.font_for_family_and_style(fam, use_bold, use_italic)

    # 3. Font Size: EXACTLY match original size by default (as user requested)
    if font_size is not None and float(font_size) > 0:
        final_size = float(font_size)
    else:
        final_size = float(span.get("size", 12.0))

    # 4. Color: Match original color unless overridden
    if color_hex:
        color = font_matcher.hex_to_rgb01(color_hex)
    else:
        color = font_matcher.hex_to_rgb01(span.get("color", "#000000"))

    rotation = span.get("rotation", 0) % 360

    # 5. Position & Alignment
    text_width = fitz.get_text_length(new_text, fontname=fontname, fontsize=final_size)

    if x is not None and y is not None:
        target_x = float(x)
        target_y = float(y)
    else:
        target_x = float(span["origin"][0])
        target_y = float(span["origin"][1])

    # Apply alignment offset
    align_mode = (align or "left").lower().strip()
    if align_mode == "center":
        if x is None and span.get("bbox"):
            # Center within original span width
            center_x = (span["bbox"][0] + span["bbox"][2]) / 2.0
            target_x = center_x - (text_width / 2.0)
        else:
            target_x = target_x - (text_width / 2.0)
    elif align_mode == "right":
        if x is None and span.get("bbox"):
            target_x = span["bbox"][2] - text_width
        else:
            target_x = target_x - text_width

    # Redact / clear the original glyphs
    _clear_area(page, cover)

    # Insert the replacement text at the computed position
    origin = fitz.Point(target_x, target_y)
    insert_kwargs = dict(fontname=fontname, fontsize=final_size, color=color)
    if rotation != 0:
        page.insert_text(origin, new_text, rotate=rotation, **insert_kwargs)
    else:
        page.insert_text(origin, new_text, **insert_kwargs)

    return EditResult(success=True, warning=None, used_font_size=final_size)


def delete_text(doc: fitz.Document, page_number: int, span: dict) -> EditResult:
    """Permanently delete text in span via PDF redaction."""
    page = doc[page_number]
    bbox = fitz.Rect(span["bbox"])
    cover = fitz.Rect(
        bbox.x0 - BBOX_PADDING,
        bbox.y0 - BBOX_PADDING,
        bbox.x1 + BBOX_PADDING,
        bbox.y1 + BBOX_PADDING,
    )
    _clear_area(page, cover)
    return EditResult(success=True, warning=None, used_font_size=0)


def add_text(
    doc: fitz.Document,
    page_number: int,
    x: float,
    y: float,
    text: str,
    fontsize: float = 12.0,
    font_family: str = "sans",
    color_hex: str = "#000000",
    bold: bool = False,
    italic: bool = False,
    align: str = "left",
) -> EditResult:
    """Insert a brand-new text object at PDF point (x, y) with alignment."""
    if not text.strip():
        return EditResult(success=False, warning="Text cannot be empty.")

    page = doc[page_number]
    fontname = font_matcher.font_for_family_and_style(font_family, bold, italic)
    color = font_matcher.hex_to_rgb01(color_hex)

    text_width = fitz.get_text_length(text, fontname=fontname, fontsize=fontsize)
    target_x = float(x)
    align_mode = (align or "left").lower().strip()
    if align_mode == "center":
        target_x = target_x - (text_width / 2.0)
    elif align_mode == "right":
        target_x = target_x - text_width

    page.insert_text(
        fitz.Point(target_x, y), text, fontname=fontname, fontsize=fontsize, color=color
    )
    return EditResult(success=True, warning=None, used_font_size=fontsize)


def find_and_replace(
    doc: fitz.Document,
    search_text: str,
    replace_text_str: str,
    page_num: int | None = None,
    match_case: bool = False,
) -> int:
    """
    Search for search_text across page_num (or all pages if None) and replace
    occurrences with replace_text_str.
    Returns the total count of replacements made.
    """
    if not search_text.strip():
        return 0

    pages_to_search = [page_num] if page_num is not None else list(range(doc.page_count))
    total_replaced = 0

    flags = 0 if match_case else 2  # 2 is case-insensitive in search_for

    for pno in pages_to_search:
        if not (0 <= pno < doc.page_count):
            continue
        page = doc[pno]
        rects = page.search_for(search_text, flags=flags)
        if not rects:
            continue

        # Sort rects from bottom to top so insertions don't affect coords
        rects.sort(key=lambda r: (r.y0, r.x0), reverse=True)

        for rect in rects:
            # Clear existing text in rect
            cover = fitz.Rect(
                rect.x0 - BBOX_PADDING,
                rect.y0 - BBOX_PADDING,
                rect.x1 + BBOX_PADDING,
                rect.y1 + BBOX_PADDING,
            )
            _clear_area(page, cover)

            # Estimate font size from rect height
            calc_size = max(rect.height * 0.82, 8.0)
            baseline_y = rect.y1 - (rect.height * 0.18)

            page.insert_text(
                fitz.Point(rect.x0, baseline_y),
                replace_text_str,
                fontname="Helvetica",
                fontsize=calc_size,
                color=(0, 0, 0),
            )
            total_replaced += 1

    return total_replaced
