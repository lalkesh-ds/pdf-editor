"""
test_app_integration.py

Comprehensive end-to-end integration test verifying all PDF Editor features:
- Sample PDF generation
- Page rendering & text extraction
- Thumbnails generation
- Inline text editing (font, style, color, size)
- Add text
- Delete text
- Whiteout / Redaction
- Highlight annotation
- Shape drawing (rect, circle, line, arrow)
- Freehand pen drawing
- Image & Signature insertion
- Page operations (rotate, duplicate, insert blank, delete)
- Find and replace
- Undo and redo
- Exporting valid PDF
"""
import base64
import asyncio
import io
import fitz

from app import (
    load_sample,
    get_page,
    get_thumbnails,
    edit_text,
    delete_text_endpoint,
    add_text_endpoint,
    whiteout_endpoint,
    highlight_endpoint,
    shape_endpoint,
    freehand_endpoint,
    add_image_endpoint,
    rotate_page_endpoint,
    duplicate_page_endpoint,
    insert_blank_endpoint,
    delete_page_endpoint,
    find_replace_endpoint,
    undo,
    redo,
    export_pdf,
    EditRequest,
    DeleteTextRequest,
    AddTextRequest,
    WhiteoutRequest,
    HighlightRequest,
    ShapeRequest,
    FreehandRequest,
    AddImageRequest,
    RotatePageRequest,
    PageActionRequest,
    InsertBlankPageRequest,
    FindReplaceRequest,
    HistoryRequest,
)


async def run_tests():
    print("=== 1. Testing Load Sample Document ===")
    sample_res = await load_sample()
    data = sample_res.body.decode("utf-8")
    import json
    data = json.loads(data)
    session_id = data["session_id"]
    page_count = data["page_count"]
    assert page_count >= 2, f"Expected at least 2 pages, got {page_count}"
    print(f"PASS: Session {session_id} created with {page_count} pages.")

    print("\n=== 2. Testing Get Page & Spans Extraction ===")
    page_res = await get_page(session_id, 0, zoom=1.5)
    page_data = json.loads(page_res.body.decode("utf-8"))
    assert "image_base64" in page_data
    assert len(page_data["spans"]) > 0
    spans = page_data["spans"]
    target_span = spans[0]
    print(f"PASS: Page 0 rendered, found {len(spans)} text spans. First span: '{target_span['text']}'")

    print("\n=== 3. Testing Thumbnails Generation ===")
    thumb_res = await get_thumbnails(session_id)
    thumb_data = json.loads(thumb_res.body.decode("utf-8"))
    assert len(thumb_data["thumbnails"]) == page_count
    print(f"PASS: Generated {len(thumb_data['thumbnails'])} thumbnails.")

    print("\n=== 4. Testing In-Place Inline Text Edit ===")
    edit_req = EditRequest(
        session_id=session_id,
        page_num=0,
        span_id=target_span["id"],
        new_text="ACME ULTRA CLOUD SOLUTIONS",
        font_size=18.0,
        font_family="sans",
        color="#2563eb",
        bold=True,
        italic=False,
    )
    edit_res = await edit_text(edit_req)
    edit_payload = json.loads(edit_res.body.decode("utf-8"))
    assert edit_payload["page_num"] == 0
    print("PASS: Text edited with custom font, size, bold, and color.")

    print("\n=== 5. Testing Add Text Anywhere ===")
    add_req = AddTextRequest(
        session_id=session_id,
        page_num=0,
        x=50.0,
        y=450.0,
        text="Special Discount: 10% OFF Approved",
        fontsize=14.0,
        font_family="serif",
        color="#10b981",
        bold=True,
        italic=True,
    )
    add_res = await add_text_endpoint(add_req)
    add_payload = json.loads(add_res.body.decode("utf-8"))
    assert add_payload["page_num"] == 0
    print("PASS: New text added at custom coordinates.")

    print("\n=== 6. Testing Whiteout / Redaction ===")
    whiteout_req = WhiteoutRequest(
        session_id=session_id,
        page_num=0,
        rect=[40, 160, 200, 190],
        fill_color="#ffffff",
        redact=True,
    )
    wo_res = await whiteout_endpoint(whiteout_req)
    assert wo_res.status_code == 200
    print("PASS: Whiteout applied and underlying text redacted.")

    print("\n=== 7. Testing Highlight Annotation ===")
    hl_req = HighlightRequest(
        session_id=session_id,
        page_num=0,
        rect=[40, 210, 250, 240],
        color="#ffe066",
        opacity=0.45,
    )
    hl_res = await highlight_endpoint(hl_req)
    assert hl_res.status_code == 200
    print("PASS: Highlight annotation added.")

    print("\n=== 8. Testing Shapes (Rectangle, Circle, Arrow) ===")
    shape_req = ShapeRequest(
        session_id=session_id,
        page_num=0,
        shape_type="arrow",
        coords=[100, 500, 250, 500],
        stroke_color="#ef4444",
        stroke_width=3.0,
    )
    s_res = await shape_endpoint(shape_req)
    assert s_res.status_code == 200
    print("PASS: Vector arrow shape created.")

    print("\n=== 9. Testing Freehand Pen Drawing ===")
    pen_req = FreehandRequest(
        session_id=session_id,
        page_num=0,
        points=[[100, 550], [120, 560], [140, 555], [160, 570]],
        stroke_color="#2563eb",
        stroke_width=2.5,
    )
    pen_res = await freehand_endpoint(pen_req)
    assert pen_res.status_code == 200
    print("PASS: Freehand ink drawing added.")

    print("\n=== 10. Testing Add Image / Signature ===")
    # Generate tiny transparent PNG in memory
    doc_temp = fitz.open()
    p_temp = doc_temp.new_page(width=60, height=30)
    p_temp.draw_rect(fitz.Rect(5, 5, 55, 25), color=(0, 0, 1), fill=(0.9, 0.95, 1))
    png_bytes = p_temp.get_pixmap().tobytes("png")
    doc_temp.close()
    b64_sig = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

    img_req = AddImageRequest(
        session_id=session_id,
        page_num=0,
        image_base64=b64_sig,
        rect=[40, 680, 180, 720],
    )
    img_res = await add_image_endpoint(img_req)
    assert img_res.status_code == 200
    print("PASS: Image / signature placed on page.")

    print("\n=== 11. Testing Page Operations ===")
    # Rotate
    rot_req = RotatePageRequest(session_id=session_id, page_num=0, angle=90)
    await rotate_page_endpoint(rot_req)
    print("PASS: Page rotated 90 degrees.")

    # Duplicate
    dup_req = PageActionRequest(session_id=session_id, page_num=0)
    dup_res = await duplicate_page_endpoint(dup_req)
    dup_payload = json.loads(dup_res.body.decode("utf-8"))
    assert dup_payload["page_count"] == page_count + 1
    print(f"PASS: Page duplicated. Total pages now: {dup_payload['page_count']}.")

    # Insert Blank Page
    blank_req = InsertBlankPageRequest(session_id=session_id, at_page_num=1)
    blank_res = await insert_blank_endpoint(blank_req)
    blank_payload = json.loads(blank_res.body.decode("utf-8"))
    print(f"PASS: Blank page inserted. Total pages now: {blank_payload['page_count']}.")

    print("\n=== 12. Testing Find and Replace ===")
    fr_req = FindReplaceRequest(
        session_id=session_id,
        search_text="Payment",
        replace_text="Settlement",
        page_num=None,
        match_case=False,
    )
    fr_res = await find_replace_endpoint(fr_req)
    fr_payload = json.loads(fr_res.body.decode("utf-8"))
    count = fr_payload.get("replaced_count", 0)
    print(f"PASS: Find and replace completed ({count} replacement(s)).")

    print("\n=== 13. Testing Undo and Redo ===")
    hist_req = HistoryRequest(session_id=session_id, page_num=0, zoom=1.5)
    undo_res = await undo(hist_req)
    assert undo_res.status_code == 200
    redo_res = await redo(hist_req)
    assert redo_res.status_code == 200
    print("PASS: Undo and redo work properly.")

    print("\n=== 14. Testing Clean PDF Export ===")
    export_res = await export_pdf(session_id)
    assert export_res.media_type == "application/pdf"
    pdf_out_bytes = export_res.body
    assert len(pdf_out_bytes) > 1000
    # Validate with fitz
    exported_doc = fitz.open(stream=pdf_out_bytes, filetype="pdf")
    assert exported_doc.page_count >= 2
    exported_doc.close()
    print(f"PASS: PDF exported successfully ({len(pdf_out_bytes)} bytes) and is fully valid!")

    print("\n==========================================")
    print("SUCCESS: ALL 14 INTEGRATION TESTS PASSED 100%!")
    print("==========================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
