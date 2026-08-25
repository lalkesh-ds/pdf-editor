"""
Local PDF Text Editor - FastAPI application.

Runs entirely on localhost. No uploaded PDF is ever sent anywhere
except processed in-memory on this machine. There is no database, no
user accounts, and no telemetry.

Start with:
    uvicorn app:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import base64
import io
import logging
import uuid
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pdf_editor import pdf_loader, pdf_exporter, text_editor, text_extractor
from pdf_editor.edit_history import EditHistory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("local_pdf_editor")

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Local PDF Text Editor")

# ---------------------------------------------------------------------------
# In-memory session store. One entry per uploaded document. Nothing here is
# written to disk or a database - it lives only for the life of the process.
# ---------------------------------------------------------------------------
SESSIONS: dict[str, dict] = {}


class EditRequest(BaseModel):
    session_id: str
    page_num: int
    span_id: str
    new_text: str
    font_size: Optional[float] = None


class AddTextRequest(BaseModel):
    session_id: str
    page_num: int
    x: float
    y: float
    text: str
    fontsize: float = 12.0
    color: str = "#000000"
    bold: bool = False
    italic: bool = False


class HistoryRequest(BaseModel):
    session_id: str
    page_num: int
    zoom: float = 1.5


def _get_session(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please upload the PDF again.",
        )
    return session


def _open_working_doc(session: dict) -> fitz.Document:
    """Open a fresh fitz.Document from the session's current committed bytes."""
    return fitz.open(stream=session["history"].current, filetype="pdf")


def _page_payload(doc: fitz.Document, page_num: int, zoom: float) -> dict:
    if page_num < 0 or page_num >= doc.page_count:
        raise HTTPException(status_code=400, detail="Page number out of range.")
    page = doc[page_num]
    png_bytes, width_px, height_px = pdf_exporter.render_page_png_sized(page, zoom)
    spans = text_extractor.extract_page_spans(page)
    is_scanned = pdf_loader.page_is_likely_scanned(page)
    rect = page.rect
    return {
        "page_num": page_num,
        "page_count": doc.page_count,
        "image_base64": base64.b64encode(png_bytes).decode("ascii"),
        "image_width": width_px,
        "image_height": height_px,
        "page_width": round(rect.width, 2),
        "page_height": round(rect.height, 2),
        "zoom": zoom,
        "spans": spans,
        "is_scanned": is_scanned,
    }


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file.")

    raw = await file.read()

    try:
        doc = pdf_loader.validate_and_open(raw)
    except pdf_loader.InvalidPDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Re-serialize once so the working copy is a clean, decrypted document
    # even if the source had an empty-password encryption wrapper.
    normalized_bytes = doc.tobytes(garbage=0, deflate=True, clean=False)
    pages = pdf_loader.get_page_dimensions(doc)
    page_count = doc.page_count
    doc.close()

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "filename": file.filename,
        "original_bytes": raw,
        "history": EditHistory(normalized_bytes),
    }

    log.info("Loaded '%s' (%d pages) as session %s", file.filename, page_count, session_id)

    return JSONResponse(
        {
            "session_id": session_id,
            "filename": file.filename,
            "page_count": page_count,
            "pages": pages,
        }
    )


@app.get("/api/page/{session_id}/{page_num}")
async def get_page(session_id: str, page_num: int, zoom: float = 1.5) -> JSONResponse:
    session = _get_session(session_id)
    doc = _open_working_doc(session)
    try:
        payload = _page_payload(doc, page_num, zoom)
    finally:
        doc.close()
    return JSONResponse(payload)


@app.post("/api/edit")
async def edit_text(req: EditRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        if req.page_num < 0 or req.page_num >= doc.page_count:
            raise HTTPException(status_code=400, detail="Page number out of range.")

        page = doc[req.page_num]
        span = text_extractor.find_span_by_id(page, req.span_id)
        if span is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "That text could not be found anymore - the page may "
                    "have changed since it was last loaded. Please refresh "
                    "the page view and try again."
                ),
            )

        mapped_font = None
        try:
            from pdf_editor import font_matcher

            mapped_font = font_matcher.map_to_base14(span["font"], 0)
            log.info(
                "Font match: '%s' -> '%s' (span %s)",
                span["font"], mapped_font, span["id"],
            )
        except Exception:
            pass

        result = text_editor.replace_text(
            doc, req.page_num, span, req.new_text, font_size=req.font_size
        )
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()

    payload["warning"] = result.warning
    payload["used_font_size"] = result.used_font_size
    return JSONResponse(payload)


@app.post("/api/add_text")
async def add_text(req: AddTextRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        if req.page_num < 0 or req.page_num >= doc.page_count:
            raise HTTPException(status_code=400, detail="Page number out of range.")

        result = text_editor.add_text(
            doc,
            req.page_num,
            req.x,
            req.y,
            req.text,
            fontsize=req.fontsize,
            color_hex=req.color,
            bold=req.bold,
            italic=req.italic,
        )
        if not result.success:
            raise HTTPException(status_code=400, detail=result.warning or "Could not add text.")

        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()

    payload["warning"] = result.warning
    return JSONResponse(payload)


@app.post("/api/undo")
async def undo(req: HistoryRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    session["history"].undo()
    doc = _open_working_doc(session)
    try:
        payload = _page_payload(doc, req.page_num, req.zoom)
    finally:
        doc.close()
    return JSONResponse(payload)


@app.post("/api/redo")
async def redo(req: HistoryRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    session["history"].redo()
    doc = _open_working_doc(session)
    try:
        payload = _page_payload(doc, req.page_num, req.zoom)
    finally:
        doc.close()
    return JSONResponse(payload)


@app.get("/api/export/{session_id}")
async def export_pdf(session_id: str) -> Response:
    session = _get_session(session_id)
    pdf_bytes = session["history"].current

    original_name = Path(session["filename"]).stem
    out_name = f"{original_name}_edited.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "active_sessions": len(SESSIONS)}
