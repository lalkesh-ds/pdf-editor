"""
sample_doc.py

Generates a realistic sample PDF with text, tables, styles, and signature fields
for immediate live testing of the PDF editor.
"""
from __future__ import annotations

import fitz  # PyMuPDF


def generate_sample_pdf() -> bytes:
    """Generate a clean 2-page sample business document as PDF bytes."""
    doc = fitz.open()

    # --- Page 1: Service Proposal & Invoice ---
    p1 = doc.new_page(width=595, height=842)  # A4 size

    # Header decorative bar
    s1 = p1.new_shape()
    s1.draw_rect(fitz.Rect(0, 0, 595, 8))
    s1.finish(color=(0.12, 0.45, 0.9), fill=(0.12, 0.45, 0.9))
    s1.commit()

    # Document Title & Company
    p1.insert_text(fitz.Point(40, 50), "ACME CLOUD SOLUTIONS", fontname="Helvetica-Bold", fontsize=20, color=(0.1, 0.15, 0.25))
    p1.insert_text(fitz.Point(40, 70), "Professional Software Development & Cloud Consulting", fontname="Helvetica", fontsize=10, color=(0.4, 0.45, 0.55))

    # Meta box on right
    p1.insert_text(fitz.Point(420, 50), "INVOICE / AGREEMENT", fontname="Helvetica-Bold", fontsize=12, color=(0.12, 0.45, 0.9))
    p1.insert_text(fitz.Point(420, 68), "Doc ID: #INV-2026-8941", fontname="Helvetica", fontsize=9, color=(0.3, 0.3, 0.3))
    p1.insert_text(fitz.Point(420, 82), "Date: October 24, 2026", fontname="Helvetica", fontsize=9, color=(0.3, 0.3, 0.3))

    # Divider line
    s_div = p1.new_shape()
    s_div.draw_line(fitz.Point(40, 95), fitz.Point(555, 95))
    s_div.finish(color=(0.85, 0.87, 0.9), width=1)
    s_div.commit()

    # Client Info Box
    p1.insert_text(fitz.Point(40, 120), "BILLED TO:", fontname="Helvetica-Bold", fontsize=9, color=(0.4, 0.45, 0.55))
    p1.insert_text(fitz.Point(40, 136), "Global Innovations Corp.", fontname="Helvetica-Bold", fontsize=12, color=(0.1, 0.1, 0.1))
    p1.insert_text(fitz.Point(40, 152), "Attn: Sarah Jenkins, VP Operations", fontname="Helvetica", fontsize=10, color=(0.25, 0.25, 0.25))
    p1.insert_text(fitz.Point(40, 166), "450 Enterprise Parkway, Suite 800", fontname="Helvetica", fontsize=10, color=(0.25, 0.25, 0.25))
    p1.insert_text(fitz.Point(40, 180), "Austin, TX 78701", fontname="Helvetica", fontsize=10, color=(0.25, 0.25, 0.25))

    # Project Description Paragraph
    p1.insert_text(fitz.Point(40, 215), "Project Overview & Scope:", fontname="Helvetica-Bold", fontsize=11, color=(0.12, 0.45, 0.9))
    intro_text = (
        "This document confirms the agreed milestones for the Q4 Enterprise Platform upgrade. "
        "The deliverables include full API integration, front-end optimization, and automated CI/CD pipeline deployment."
    )
    p1.insert_textbox(fitz.Rect(40, 225, 555, 260), intro_text, fontname="Times-Roman", fontsize=10.5, color=(0.2, 0.2, 0.2))

    # Table Header
    th_shape = p1.new_shape()
    th_shape.draw_rect(fitz.Rect(40, 275, 555, 298))
    th_shape.finish(color=(0.92, 0.94, 0.98), fill=(0.92, 0.94, 0.98))
    th_shape.commit()

    p1.insert_text(fitz.Point(50, 291), "Description", fontname="Helvetica-Bold", fontsize=9.5, color=(0.15, 0.2, 0.3))
    p1.insert_text(fitz.Point(320, 291), "Hours", fontname="Helvetica-Bold", fontsize=9.5, color=(0.15, 0.2, 0.3))
    p1.insert_text(fitz.Point(400, 291), "Rate ($/hr)", fontname="Helvetica-Bold", fontsize=9.5, color=(0.15, 0.2, 0.3))
    p1.insert_text(fitz.Point(490, 291), "Amount", fontname="Helvetica-Bold", fontsize=9.5, color=(0.15, 0.2, 0.3))

    # Table Rows
    rows = [
        ("Architecture Design & Schema Migration", "30", "$150.00", "$4,500.00"),
        ("REST API & Microservices Implementation", "55", "$140.00", "$7,700.00"),
        ("Interactive Web Dashboard Development", "45", "$130.00", "$5,850.00"),
        ("Automated QA Testing & Deployment", "20", "$125.00", "$2,500.00"),
    ]

    y = 320
    for desc, hrs, rate, amt in rows:
        p1.insert_text(fitz.Point(50, y), desc, fontname="Helvetica", fontsize=9.5, color=(0.15, 0.15, 0.15))
        p1.insert_text(fitz.Point(330, y), hrs, fontname="Courier", fontsize=9.5, color=(0.15, 0.15, 0.15))
        p1.insert_text(fitz.Point(405, y), rate, fontname="Courier", fontsize=9.5, color=(0.15, 0.15, 0.15))
        p1.insert_text(fitz.Point(495, y), amt, fontname="Courier-Bold", fontsize=9.5, color=(0.1, 0.1, 0.1))

        # row underline
        s_row = p1.new_shape()
        s_row.draw_line(fitz.Point(40, y + 8), fitz.Point(555, y + 8))
        s_row.finish(color=(0.92, 0.92, 0.94), width=0.75)
        s_row.commit()
        y += 28

    # Totals Section
    p1.insert_text(fitz.Point(380, y + 10), "Subtotal:", fontname="Helvetica", fontsize=10, color=(0.3, 0.3, 0.3))
    p1.insert_text(fitz.Point(490, y + 10), "$20,550.00", fontname="Courier", fontsize=10, color=(0.2, 0.2, 0.2))

    p1.insert_text(fitz.Point(380, y + 28), "Tax (8.25%):", fontname="Helvetica", fontsize=10, color=(0.3, 0.3, 0.3))
    p1.insert_text(fitz.Point(490, y + 28), "$1,695.38", fontname="Courier", fontsize=10, color=(0.2, 0.2, 0.2))

    # Total Box
    tot_shape = p1.new_shape()
    tot_shape.draw_rect(fitz.Rect(370, y + 42, 555, y + 70))
    tot_shape.finish(color=(0.12, 0.45, 0.9), fill=(0.95, 0.97, 1.0), width=1)
    tot_shape.commit()

    p1.insert_text(fitz.Point(380, y + 61), "TOTAL DUE:", fontname="Helvetica-Bold", fontsize=11, color=(0.12, 0.45, 0.9))
    p1.insert_text(fitz.Point(485, y + 61), "$22,245.38", fontname="Courier-Bold", fontsize=11.5, color=(0.1, 0.1, 0.1))

    # Signature Area
    sig_y = y + 150
    p1.insert_text(fitz.Point(40, sig_y), "Authorized Signature:", fontname="Helvetica-Bold", fontsize=10, color=(0.3, 0.35, 0.4))
    p1.insert_text(fitz.Point(340, sig_y), "Client Approval Signature:", fontname="Helvetica-Bold", fontsize=10, color=(0.3, 0.35, 0.4))

    sig_line = p1.new_shape()
    sig_line.draw_line(fitz.Point(40, sig_y + 40), fitz.Point(240, sig_y + 40))
    sig_line.draw_line(fitz.Point(340, sig_y + 40), fitz.Point(540, sig_y + 40))
    sig_line.finish(color=(0.7, 0.7, 0.7), width=1)
    sig_line.commit()

    p1.insert_text(fitz.Point(40, sig_y + 54), "Date: 10/24/2026", fontname="Helvetica", fontsize=8.5, color=(0.4, 0.4, 0.4))
    p1.insert_text(fitz.Point(340, sig_y + 54), "Date: ______________", fontname="Helvetica", fontsize=8.5, color=(0.4, 0.4, 0.4))

    # Footer
    p1.insert_text(fitz.Point(40, 805), "Thank you for your business! Please remit payment within 30 days.", fontname="Helvetica-Oblique", fontsize=8.5, color=(0.5, 0.5, 0.5))
    p1.insert_text(fitz.Point(480, 805), "Page 1 of 2", fontname="Helvetica", fontsize=8.5, color=(0.5, 0.5, 0.5))

    # --- Page 2: Terms of Service & Notes ---
    p2 = doc.new_page(width=595, height=842)

    # Decorative bar
    s2 = p2.new_shape()
    s2.draw_rect(fitz.Rect(0, 0, 595, 8))
    s2.finish(color=(0.12, 0.45, 0.9), fill=(0.12, 0.45, 0.9))
    s2.commit()

    p2.insert_text(fitz.Point(40, 50), "TERMS OF SERVICE & WARRANTIES", fontname="Helvetica-Bold", fontsize=16, color=(0.1, 0.15, 0.25))

    terms = [
        ("1. Payment Terms", "Invoices are payable within net 30 days from date of receipt. Late balances may accrue 1.5% interest per month."),
        ("2. Intellectual Property", "All custom deliverables created under this agreement become the exclusive property of Client upon final settlement."),
        ("3. Confidentiality", "Both parties agree to protect proprietary code, trade secrets, and internal databases with reasonable commercial care."),
        ("4. Warranty Period", "ACME warrants code quality for 90 days following production launch. Critical bugs will be resolved promptly at no fee."),
    ]

    ty = 90
    for heading, text in terms:
        p2.insert_text(fitz.Point(40, ty), heading, fontname="Helvetica-Bold", fontsize=11, color=(0.12, 0.45, 0.9))
        p2.insert_textbox(fitz.Rect(40, ty + 8, 555, ty + 45), text, fontname="Times-Roman", fontsize=10, color=(0.25, 0.25, 0.25))
        ty += 65

    # Footer
    p2.insert_text(fitz.Point(40, 805), "ACME Solutions Inc. — Confidential & Proprietary", fontname="Helvetica-Oblique", fontsize=8.5, color=(0.5, 0.5, 0.5))
    p2.insert_text(fitz.Point(480, 805), "Page 2 of 2", fontname="Helvetica", fontsize=8.5, color=(0.5, 0.5, 0.5))

    pdf_bytes = doc.tobytes(garbage=0, deflate=True)
    doc.close()
    return pdf_bytes
