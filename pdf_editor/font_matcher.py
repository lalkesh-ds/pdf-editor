"""
font_matcher.py

PDF fonts are frequently embedded, subsetted (names like
"ABCDEF+Calibri"), or use internal PostScript names that don't exist
as installed system fonts. Reusing the exact embedded font program for
freshly-typeset text is unreliable across PDFs, so this editor maps
every extracted font to the closest of PyMuPDF's 14 built-in "Base14"
fonts, preserving bold/italic styling and serif/mono family as
faithfully as possible.

This trades perfect font fidelity for reliability - documented as a
known limitation in the README.
"""
from __future__ import annotations

import re

# PyMuPDF built-in Base14 font names (no external font files needed).
# These exact strings are what fitz.Page.insert_text/insert_textbox expect.
_SERIF = {
    (False, False): "Times-Roman",
    (True, False): "Times-Bold",
    (False, True): "Times-Italic",
    (True, True): "Times-BoldItalic",
}
_SANS = {
    (False, False): "Helvetica",
    (True, False): "Helvetica-Bold",
    (False, True): "Helvetica-Oblique",
    (True, True): "Helvetica-BoldOblique",
}
_MONO = {
    (False, False): "Courier",
    (True, False): "Courier-Bold",
    (False, True): "Courier-Oblique",
    (True, True): "Courier-BoldOblique",
}

_SERIF_HINTS = re.compile(
    r"(times|serif|georgia|garamond|cambria|book|minion|palatino|"
    r"caslon|constantia)",
    re.IGNORECASE,
)
_MONO_HINTS = re.compile(
    r"(courier|mono|consolas|typewriter|menlo)", re.IGNORECASE
)
_BOLD_HINTS = re.compile(r"bold|black|heavy|semibold", re.IGNORECASE)
_ITALIC_HINTS = re.compile(r"italic|oblique", re.IGNORECASE)


def strip_subset_prefix(fontname: str) -> str:
    """'ABCDEF+Calibri-Bold' -> 'Calibri-Bold' (subset tag is 6 caps + '+')."""
    if len(fontname) > 7 and fontname[6] == "+" and fontname[:6].isupper():
        return fontname[7:]
    return fontname


def detect_bold_italic(fontname: str, span_flags: int) -> tuple[bool, bool]:
    """
    Combine PyMuPDF's span flag bits with a name-based heuristic, since
    flags are not always reliable for every producer.

    span flags bit meaning (PyMuPDF): bit 0 superscript, bit 1 italic,
    bit 2 serifed, bit 3 monospaced, bit 4 bold.
    """
    name = fontname or ""
    is_bold = bool(span_flags & (1 << 4)) or bool(_BOLD_HINTS.search(name))
    is_italic = bool(span_flags & (1 << 1)) or bool(_ITALIC_HINTS.search(name))
    return is_bold, is_italic


def map_to_base14(fontname: str, span_flags: int = 0) -> str:
    """
    Map an extracted PDF font name to the closest Base14 built-in font
    code understood by fitz's insert_text / insert_textbox.
    """
    clean = strip_subset_prefix(fontname or "")
    is_bold, is_italic = detect_bold_italic(clean, span_flags)

    if _MONO_HINTS.search(clean) or bool(span_flags & (1 << 3)):
        table = _MONO
    elif _SERIF_HINTS.search(clean) or bool(span_flags & (1 << 2)):
        table = _SERIF
    else:
        table = _SANS

    chosen = table[(is_bold, is_italic)]
    return chosen


def color_int_to_rgb01(color_int: int) -> tuple[float, float, float]:
    """PyMuPDF span['color'] is a packed 24-bit int -> (r, g, b) in 0..1."""
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)


def sans_font_for_style(bold: bool, italic: bool) -> str:
    """Base14 sans-serif font name for the given bold/italic combo."""
    return _SANS[(bold, italic)]


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return (0.0, 0.0, 0.0)
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)
