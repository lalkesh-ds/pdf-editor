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
import os
import time
import uuid
from pathlib import Path
from typing import Optional, List

import fitz  # PyMuPDF
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pdf_editor import (
    pdf_loader,
    pdf_exporter,
    text_editor,
    text_extractor,
    page_ops,
    annotations,
)
from pdf_editor.edit_history import EditHistory
from pdf_editor.sample_doc import generate_sample_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("local_pdf_editor")

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Local PDF Studio")

# CORS middleware for web service deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store with automated cloud lifecycle management
# ---------------------------------------------------------------------------
SESSIONS: dict[str, dict] = {}
MAX_SESSION_AGE_SECONDS = 7200  # 2 hours
MAX_TOTAL_SESSIONS = 100
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _cleanup_old_sessions() -> None:
    """Purge stale sessions to prevent out-of-memory errors on cloud hosts."""
    now = time.time()
    expired = [
        sid for sid, sess in SESSIONS.items()
        if now - sess.get("last_accessed", now) > MAX_SESSION_AGE_SECONDS
    ]
    for sid in expired:
        del SESSIONS[sid]

    # If still exceeding capacity under heavy load, remove oldest
    if len(SESSIONS) > MAX_TOTAL_SESSIONS:
        sorted_sids = sorted(SESSIONS.keys(), key=lambda s: SESSIONS[s].get("last_accessed", 0))
        for sid in sorted_sids[:len(SESSIONS) - MAX_TOTAL_SESSIONS]:
            del SESSIONS[sid]


# --- Request Models ---

class EditRequest(BaseModel):
    session_id: str
    page_num: int
    span_id: str
    new_text: str
    font_size: Optional[float] = None
    font_family: Optional[str] = None
    color: Optional[str] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    x: Optional[float] = None
    y: Optional[float] = None
    align: Optional[str] = "left"


class DeleteTextRequest(BaseModel):
    session_id: str
    page_num: int
    span_id: str


class AddTextRequest(BaseModel):
    session_id: str
    page_num: int
    x: float
    y: float
    text: str
    fontsize: float = 12.0
    font_family: str = "sans"
    color: str = "#000000"
    bold: bool = False
    italic: bool = False
    align: Optional[str] = "left"


class WhiteoutRequest(BaseModel):
    session_id: str
    page_num: int
    rect: list[float]  # [x0, y0, x1, y1]
    fill_color: str = "#ffffff"
    redact: bool = True


class HighlightRequest(BaseModel):
    session_id: str
    page_num: int
    rect: list[float]  # [x0, y0, x1, y1]
    color: str = "#ffe066"
    opacity: float = 0.45


class ShapeRequest(BaseModel):
    session_id: str
    page_num: int
    shape_type: str  # "rect", "circle", "line", "arrow"
    coords: list[float]  # [x0, y0, x1, y1]
    stroke_color: str = "#000000"
    fill_color: Optional[str] = None
    stroke_width: float = 2.0
    opacity: float = 1.0


class FreehandRequest(BaseModel):
    session_id: str
    page_num: int
    points: list[list[float]]  # [[x, y], ...]
    stroke_color: str = "#000000"
    stroke_width: float = 2.0
    opacity: float = 1.0


class AddImageRequest(BaseModel):
    session_id: str
    page_num: int
    image_base64: str
    rect: list[float]  # [x0, y0, x1, y1]


class RotatePageRequest(BaseModel):
    session_id: str
    page_num: int
    angle: int = 90


class PageActionRequest(BaseModel):
    session_id: str
    page_num: int


class InsertBlankPageRequest(BaseModel):
    session_id: str
    at_page_num: Optional[int] = None


class MovePageRequest(BaseModel):
    session_id: str
    from_idx: int
    to_idx: int


class FindReplaceRequest(BaseModel):
    session_id: str
    search_text: str
    replace_text: str
    page_num: Optional[int] = None
    match_case: bool = False


class HistoryRequest(BaseModel):
    session_id: str
    page_num: int
    zoom: float = 1.5


# --- Helpers ---

def _get_session(session_id: str) -> dict:
    _cleanup_old_sessions()
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload or open the PDF again.",
        )
    session["last_accessed"] = time.time()
    return session


def _open_working_doc(session: dict) -> fitz.Document:
    """Open a fresh fitz.Document from the session's current committed bytes."""
    return fitz.open(stream=session["history"].current, filetype="pdf")


def _page_payload(doc: fitz.Document, page_num: int, zoom: float) -> dict:
    if page_num < 0 or page_num >= doc.page_count:
        page_num = max(0, min(page_num, doc.page_count - 1))
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
        "rotation": page.rotation,
        "zoom": zoom,
        "spans": spans,
        "is_scanned": is_scanned,
    }


def _thumbnails_payload(doc: fitz.Document) -> list[dict]:
    thumbnails = []
    for idx, page in enumerate(doc):
        png_bytes, width_px, height_px = pdf_exporter.render_thumbnail_png(page, max_dim=150)
        thumbnails.append(
            {
                "page_num": idx,
                "image_base64": base64.b64encode(png_bytes).decode("ascii"),
                "width": width_px,
                "height": height_px,
                "rotation": page.rotation,
            }
        )
    return thumbnails


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

@app.get("/api/sample")
async def load_sample() -> JSONResponse:
    """Generate and load an interactive sample business proposal PDF."""
    raw = generate_sample_pdf()
    doc = fitz.open(stream=raw, filetype="pdf")
    normalized_bytes = doc.tobytes(garbage=0, deflate=True, clean=False)
    pages = pdf_loader.get_page_dimensions(doc)
    page_count = doc.page_count
    doc.close()

    session_id = str(uuid.uuid4())
    now = time.time()
    SESSIONS[session_id] = {
        "filename": "sample_proposal.pdf",
        "original_bytes": raw,
        "history": EditHistory(normalized_bytes),
        "created_at": now,
        "last_accessed": now,
    }

    return JSONResponse(
        {
            "session_id": session_id,
            "filename": "sample_proposal.pdf",
            "page_count": page_count,
            "pages": pages,
        }
    )


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file.")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum supported upload size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB.",
        )

    try:
        doc = pdf_loader.validate_and_open(raw)
    except pdf_loader.InvalidPDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_bytes = doc.tobytes(garbage=0, deflate=True, clean=False)
    pages = pdf_loader.get_page_dimensions(doc)
    page_count = doc.page_count
    doc.close()

    _cleanup_old_sessions()
    session_id = str(uuid.uuid4())
    now = time.time()
    SESSIONS[session_id] = {
        "filename": file.filename,
        "original_bytes": raw,
        "history": EditHistory(normalized_bytes),
        "created_at": now,
        "last_accessed": now,
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


@app.get("/api/thumbnails/{session_id}")
async def get_thumbnails(session_id: str) -> JSONResponse:
    session = _get_session(session_id)
    doc = _open_working_doc(session)
    try:
        thumbs = _thumbnails_payload(doc)
    finally:
        doc.close()
    return JSONResponse({"thumbnails": thumbs, "page_count": len(thumbs)})


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
                detail="Text span not found. The page may have changed; please refresh.",
            )

        result = text_editor.replace_text(
            doc,
            req.page_num,
            span,
            req.new_text,
            font_size=req.font_size,
            font_family=req.font_family,
            color_hex=req.color,
            bold=req.bold,
            italic=req.italic,
            x=req.x,
            y=req.y,
            align=req.align,
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


@app.post("/api/delete_text")
async def delete_text_endpoint(req: DeleteTextRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        if req.page_num < 0 or req.page_num >= doc.page_count:
            raise HTTPException(status_code=400, detail="Page number out of range.")

        page = doc[req.page_num]
        span = text_extractor.find_span_by_id(page, req.span_id)
        if span is None:
            raise HTTPException(status_code=404, detail="Text span not found.")

        result = text_editor.delete_text(doc, req.page_num, span)
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()

    return JSONResponse(payload)


@app.post("/api/add_text")
async def add_text_endpoint(req: AddTextRequest) -> JSONResponse:
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
            font_family=req.font_family,
            color_hex=req.color,
            bold=req.bold,
            italic=req.italic,
            align=req.align or "left",
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


@app.post("/api/whiteout")
async def whiteout_endpoint(req: WhiteoutRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        ok = annotations.add_whiteout(
            doc, req.page_num, req.rect, fill_hex=req.fill_color, redact_text=req.redact
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Could not apply whiteout.")
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/highlight")
async def highlight_endpoint(req: HighlightRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        ok = annotations.add_highlight(
            doc, req.page_num, req.rect, color_hex=req.color, opacity=req.opacity
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Could not apply highlight.")
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/shape")
async def shape_endpoint(req: ShapeRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        ok = annotations.add_shape(
            doc,
            req.page_num,
            req.shape_type,
            req.coords,
            stroke_hex=req.stroke_color,
            fill_hex=req.fill_color,
            stroke_width=req.stroke_width,
            opacity=req.opacity,
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Could not draw shape.")
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/freehand")
async def freehand_endpoint(req: FreehandRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        ok = annotations.add_freehand(
            doc,
            req.page_num,
            req.points,
            stroke_hex=req.stroke_color,
            stroke_width=req.stroke_width,
            opacity=req.opacity,
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Could not draw freehand annotation.")
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/add_image")
async def add_image_endpoint(req: AddImageRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        # Decode base64 data
        raw_b64 = req.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(raw_b64)

        ok = annotations.add_image_to_page(doc, req.page_num, img_bytes, req.rect)
        if not ok:
            raise HTTPException(status_code=400, detail="Could not add image.")
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


# --- Page Management Endpoints ---

@app.post("/api/page/rotate")
async def rotate_page_endpoint(req: RotatePageRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        page_ops.rotate_page(doc, req.page_num, req.angle)
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/page/delete")
async def delete_page_endpoint(req: PageActionRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        ok = page_ops.delete_page(doc, req.page_num)
        if not ok:
            raise HTTPException(status_code=400, detail="Cannot delete the only page in the document.")
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        new_page_num = min(req.page_num, fresh_doc.page_count - 1)
        payload = _page_payload(fresh_doc, new_page_num, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/page/duplicate")
async def duplicate_page_endpoint(req: PageActionRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        new_idx = page_ops.duplicate_page(doc, req.page_num)
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, new_idx, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/page/insert_blank")
async def insert_blank_endpoint(req: InsertBlankPageRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        target_idx = page_ops.insert_blank_page(doc, req.at_page_num)
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, target_idx, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/page/move")
async def move_page_endpoint(req: MovePageRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        page_ops.move_page(doc, req.from_idx, req.to_idx)
        new_bytes = pdf_exporter.export_pdf_bytes(doc)
        session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, req.to_idx, zoom=1.5)
    finally:
        fresh_doc.close()
    return JSONResponse(payload)


@app.post("/api/find_replace")
async def find_replace_endpoint(req: FindReplaceRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    doc = _open_working_doc(session)
    try:
        count = text_editor.find_and_replace(
            doc,
            req.search_text,
            req.replace_text,
            page_num=req.page_num,
            match_case=req.match_case,
        )
        if count > 0:
            new_bytes = pdf_exporter.export_pdf_bytes(doc)
            session["history"].push_and_commit(new_bytes)
    finally:
        doc.close()

    current_pno = req.page_num if req.page_num is not None else 0
    fresh_doc = _open_working_doc(session)
    try:
        payload = _page_payload(fresh_doc, current_pno, zoom=1.5)
    finally:
        fresh_doc.close()

    payload["replaced_count"] = count
    return JSONResponse(payload)


# --- Undo / Redo / Export ---

@app.post("/api/undo")
async def undo(req: HistoryRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    session["history"].undo()
    doc = _open_working_doc(session)
    try:
        pno = min(req.page_num, doc.page_count - 1)
        payload = _page_payload(doc, pno, req.zoom)
        payload["can_undo"] = session["history"].can_undo()
        payload["can_redo"] = session["history"].can_redo()
    finally:
        doc.close()
    return JSONResponse(payload)


@app.post("/api/redo")
async def redo(req: HistoryRequest) -> JSONResponse:
    session = _get_session(req.session_id)
    session["history"].redo()
    doc = _open_working_doc(session)
    try:
        pno = min(req.page_num, doc.page_count - 1)
        payload = _page_payload(doc, pno, req.zoom)
        payload["can_undo"] = session["history"].can_undo()
        payload["can_redo"] = session["history"].can_redo()
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    log.info(f"Starting Local PDF Studio server on http://{host}:{port}")
    uvicorn.run("app:app", host=host, port=port)
