"""
page_ops.py

Handles PDF page-level operations using PyMuPDF:
- rotate_page: rotates a page 90, 180, 270 degrees
- delete_page: removes a page from the document
- duplicate_page: clones a page
- insert_blank_page: adds a blank page before or after
- move_page: reorders pages
"""
from __future__ import annotations

import fitz  # PyMuPDF


def rotate_page(doc: fitz.Document, page_num: int, angle: int = 90) -> None:
    """Rotate the specified page clockwise by angle degrees (default 90)."""
    if 0 <= page_num < doc.page_count:
        page = doc[page_num]
        new_rotation = (page.rotation + angle) % 360
        page.set_rotation(new_rotation)


def delete_page(doc: fitz.Document, page_num: int) -> bool:
    """Delete the specified page. Requires at least 1 page to remain."""
    if doc.page_count <= 1:
        return False
    if 0 <= page_num < doc.page_count:
        doc.delete_page(page_num)
        return True
    return False


def duplicate_page(doc: fitz.Document, page_num: int) -> int:
    """
    Duplicate the specified page and insert it right after page_num.
    Returns the index of the newly inserted page.
    """
    if 0 <= page_num < doc.page_count:
        doc.copy_page(page_num, page_num)
        return page_num + 1
    return page_num


def insert_blank_page(
    doc: fitz.Document,
    at_page_num: int | None = None,
    width: float = 595.0,
    height: float = 842.0,
) -> int:
    """
    Insert a blank page (default A4: 595x842 pt).
    If at_page_num is None, append to the end.
    Returns the index of the inserted page.
    """
    if at_page_num is None or at_page_num >= doc.page_count:
        target_idx = doc.page_count
    else:
        target_idx = max(0, at_page_num)
    doc.new_page(target_idx, width=width, height=height)
    return target_idx


def move_page(doc: fitz.Document, from_idx: int, to_idx: int) -> bool:
    """Move a page from from_idx to to_idx."""
    if 0 <= from_idx < doc.page_count and 0 <= to_idx < doc.page_count:
        if from_idx != to_idx:
            doc.move_page(from_idx, to_idx)
            return True
    return False
