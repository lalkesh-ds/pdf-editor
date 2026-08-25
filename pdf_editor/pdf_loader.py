"""
pdf_loader.py

Responsible for validating uploaded PDF bytes and opening them as
PyMuPDF (fitz) Document objects. Nothing here touches the network or
disk beyond what the caller explicitly asks for.
"""
from __future__ import annotations

import fitz  # PyMuPDF


class InvalidPDFError(Exception):
    """Raised when the uploaded file is not a usable PDF."""


def validate_and_open(pdf_bytes: bytes) -> fitz.Document:
    """
    Validate that the given bytes are a readable PDF and return an
    opened fitz.Document.

    Raises InvalidPDFError with a human-readable message on failure.
    """
    if not pdf_bytes:
        raise InvalidPDFError("The uploaded file is empty.")

    # PDF files must start with the %PDF- header per the spec (allowing
    # for a small amount of leading whitespace some tools add).
    if pdf_bytes.lstrip()[:5] != b"%PDF-":
        raise InvalidPDFError(
            "This does not look like a valid PDF file (missing %PDF header)."
        )

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises generic RuntimeError/ValueError
        raise InvalidPDFError(
            f"Could not open the PDF file. It may be corrupted or "
            f"password-protected. Details: {exc}"
        ) from exc

    if doc.is_encrypted:
        # Try an empty-password unlock (some PDFs are "encrypted" with
        # an empty owner password and are otherwise fully readable).
        if not doc.authenticate(""):
            doc.close()
            raise InvalidPDFError(
                "This PDF is password-protected. Please remove the "
                "password before editing it here."
            )

    if doc.page_count == 0:
        doc.close()
        raise InvalidPDFError("This PDF has no pages.")

    return doc


def get_page_dimensions(doc: fitz.Document) -> list[dict]:
    """Return [{width, height, rotation}] in PDF points for every page."""
    pages = []
    for page in doc:
        rect = page.rect
        pages.append(
            {
                "width": round(rect.width, 2),
                "height": round(rect.height, 2),
                "rotation": page.rotation,
            }
        )
    return pages


def page_has_extractable_text(page: fitz.Page) -> bool:
    """Cheap heuristic used to warn the user about scanned pages."""
    text = page.get_text("text").strip()
    return len(text) > 0


def page_is_likely_scanned(page: fitz.Page) -> bool:
    """
    Heuristic: a page with little/no extractable text but at least one
    large embedded image is probably a scanned page.
    """
    if page_has_extractable_text(page):
        return False
    images = page.get_images(full=True)
    return len(images) > 0
