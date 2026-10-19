"""
pdf_exporter.py

Handles turning the working fitz.Document into final export bytes,
and rendering individual pages to PNG for the editor's viewer.
"""
from __future__ import annotations

import fitz  # PyMuPDF


def render_page_png(page: fitz.Page, zoom: float = 1.5) -> bytes:
    """
    Render a page to PNG bytes at the given zoom factor (1.0 = 72 DPI).
    This is used only to display the page in the browser - the actual
    exported PDF remains a real, vector PDF, not a rasterized image.
    """
    return render_page_png_sized(page, zoom)[0]


def render_page_png_sized(
    page: fitz.Page, zoom: float = 1.5
) -> tuple[bytes, int, int]:
    """Same as render_page_png but also returns (width_px, height_px)."""
    zoom = max(0.25, min(zoom, 4.0))
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


def render_thumbnail_png(page: fitz.Page, max_dim: int = 160) -> tuple[bytes, int, int]:
    """Render a compact thumbnail image for page navigator."""
    rect = page.rect
    longest = max(rect.width, rect.height)
    if longest <= 0:
        scale = 0.2
    else:
        scale = max_dim / longest
    scale = max(0.1, min(scale, 0.5))
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


def export_pdf_bytes(doc: fitz.Document) -> bytes:
    """
    Return the current working document as PDF bytes, preserving
    structure (garbage=0 avoids unnecessary re-writing/compression of
    unrelated objects; deflate uses standard lossless PDF stream
    compression, not image recompression).
    """
    return doc.tobytes(garbage=0, deflate=True, clean=False)
