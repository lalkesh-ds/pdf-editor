# 📄 PDF Studio Pro

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PyMuPDF](https://img.shields.io/badge/PyMuPDF-1.24+-FF6F00?style=for-the-badge&logo=adobeacrobatreader&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Cloud Ready](https://img.shields.io/badge/Deploy-Render%20%7C%20Railway%20%7C%20Heroku-46E3B7?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)

**A professional, full-featured Web & Cloud PDF Editor engineered with FastAPI and PyMuPDF.**  
*Edit existing PDF text directly in-place with auto-detected font styles, reposition text with magnetic snapping guidelines, draw or type signatures, apply permanent vector redactions, draw shapes, manage pages, and export clean, high-fidelity PDFs.*

[Key Features](#-key-features) • [System Architecture](#-system-architecture) • [Live Cloud Deployment](#-cloud-deployment-guide) • [API Reference](#-api-endpoints) • [Quick Start](#-quick-start)

---

</div>

## 🌟 Overview

**PDF Studio Pro** provides true in-place WYSIWYG PDF editing right in the web browser. Unlike conventional tools that simply overlay HTML text boxes on top of images, PDF Studio Pro modifies the underlying PDF vector stream using high-performance MuPDF primitives.

Whether running locally on a personal workstation or deployed to cloud platforms (Render, Railway, AWS, DigitalOcean, Docker), PDF Studio Pro delivers a frictionless, desktop-grade editing experience with zero third-party telemetry.

---

## ✨ Key Features

### 1. In-Place WYSIWYG Text Editing
- **Direct Click-to-Edit**: Click any existing text block to convert it into a pixel-perfect inline editor at its exact baseline coordinates.
- **Auto-Detected Font & Style**:
  - Automatically identifies font family (Standard Base-14 Helvetica/Arial, Times Roman, Courier).
  - Preserves exact point size ($pt$), bold and italic weightings, and original RGB/Hex text color.
- **Magnetic Drag Repositioning**:
  - Drag text anywhere on the page with magnetic snapping to neighboring baselines, margins, and centerlines.
  - **Auto-Commit on Drop**: Release the mouse (`mouseup`) and the position commits instantly without requiring manual confirmation dialogs.
  - Sub-pixel baseline translation preserves exact vertical alignment with adjacent text blocks.
- **One-Click Text Alignment**: Quick-align to `Left`, `Center`, or `Right` with immediate document-level updates.
- **Click-to-Type Anywhere**: Click on any empty space to add new text elements on demand.

### 2. Signatures & Digital Stamps
- **Multi-Modal Signature Suite**:
  - **Draw**: Interactive HTML5 canvas with smooth Bezier curve interpolation, adjustable stroke width, and authentic ink tones (Black, Navy Blue, Forest Green).
  - **Type**: Generate elegant cursive signatures powered by Google handwriting fonts (*Great Vibes*, *Dancing Script*, *Caveat*, *Marck Script*).
  - **Upload**: Upload PNG/JPEG signature stamps or company seals with full alpha-transparency preservation.
- **Transform & Placement Box**: Drag to position anywhere, resize using corner handles with maintained aspect ratios, and commit.

### 3. True Vector Whiteout & Legal Redaction
- **Permanent Redaction**: Permanently cuts text glyphs out of the PDF stream—redacted text cannot be highlighted, selected, or inspected via dev tools.
- **Whiteout Mode**: Seamlessly matches clean white paper backgrounds.
- **Blackout Mode**: Applies high-contrast black redactions for sensitive legal, financial, or medical disclosures.

### 4. Rich Annotations & Vector Shapes
- **Text Highlighting**: Semi-transparent rectangular highlights with customizable palette (Yellow, Cyan, Emerald Green, Hot Pink).
- **Freehand Pen**: Smooth vector drawing for markups, callouts, and manual approvals.
- **Vector Shapes**: Insert crisp Rectangles, Circles/Ellipses, Lines, and Directional Arrows with adjustable stroke width and colors.

### 5. Visual Page Management & Thumbnails
- **Left Collapsible Drawer**: Live previews of every document page.
- **Page Rotation**: 90° Clockwise or Counter-Clockwise page-level rotation.
- **Page Operations**: Duplicate pages, insert blank pages before or after any page, or delete pages with safety validation.
- **Quick Jump**: Jump directly to any page via click or direct numeric input.

### 6. Document-Wide Find & Replace
- Fast search across the active page or the entire document.
- Case-sensitive and case-insensitive matching options.
- Atomically replaces all matches and reports total replacement count.

### 7. Non-Destructive Undo / Redo & Sample Document
- Comprehensive session history stack supporting keyboard shortcuts (`Ctrl+Z`, `Ctrl+Y`).
- Built-in **Sample Document Generator** (`⚡ Load Sample Proposal & Invoice PDF`) for instant 1-click live testing without needing an initial upload.
- High-fidelity lossless PDF vector export (`<filename>_edited.pdf`).

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Web Browser Client                            │
│                                                                        │
│  ┌────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │    Tool Ribbon UI      │  │        Interactive Canvas Layer      │  │
│  │ (Text, Forms, Images,  │  │  - Rendered PDF Page Image (150 DPI) │  │
│  │  Sign, Whiteout, etc.) │  │  - Interactive Span Bounding Boxes   │  │
│  └───────────┬────────────┘  │  - WYSIWYG Inline Content-Editable   │  │
│              │               │  - Magnetic Alignment Guidelines     │  │
│              │               │  - Interactive Transform & Sign Box  │  │
│              │               └──────────────────┬───────────────────┘  │
└──────────────┼──────────────────────────────────┼──────────────────────┘
               │                                  │
               │ HTTP REST Requests (JSON / FormData)
               ▼                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application Core                        │
│                                                                        │
│  ┌────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │    CORS Middleware     │  │          Session Store Manager       │  │
│  │  (Multi-Origin Access) │  │  - In-Memory Document Registry       │  │
│  └────────────────────────┘  │  - Dynamic Port & 0.0.0.0 Binding    │  │
│  ┌────────────────────────┐  │  - Auto-Cleanup & OOM Guard          │  │
│  │   Payload Size Guard   │  │  - Liveness Health Probe (/health)   │  │
│  │   (50MB Maximum Cap)   │  └──────────────────┬───────────────────┘  │
│  └────────────────────────┘                     │                      │
└─────────────────────────────────────────────────┼──────────────────────┘
                                                  │
                                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       PyMuPDF Engine (fitz) Core                       │
│                                                                        │
│  ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────┐ │
│  │  Font & Style Matcher │ │ Vector Stream Redactor│ │ Page Manager  │ │
│  │  (Base-14 Detection)  │ │ (True Glyph Deletion) │ │ (Rotate/Move) │ │
│  └───────────────────────┘ └───────────────────────┘ └───────────────┘ │
│  ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────┐ │
│  │   Annotation Engine   │ │ High-DPI Page Renderer│ │ Vector Export │ │
│  │  (Ink, Shapes, Marks) │ │ (Crisp Web Pixmaps)   │ │ (Lossless PDF)│ │
│  └───────────────────────┘ └───────────────────────┘ └───────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
├── app.py                      # FastAPI REST application & session management
├── Dockerfile                  # Production-optimized container build
├── .dockerignore               # Docker build ignore rules
├── Procfile                    # Cloud process declaration (Heroku/Render)
├── render.yaml                 # 1-Click Render.com deployment manifest
├── railway.json                # Railway.app configuration manifest
├── requirements.txt            # Python dependencies (FastAPI, PyMuPDF, Uvicorn)
├── run.bat                     # 1-click Windows launcher
├── test_app_integration.py     # 14-point automated test suite
├── pdf_editor/
│   ├── annotations.py          # Whiteout, highlights, shapes, drawings, signatures
│   ├── font_matcher.py         # Standard Base-14 font mapping & style matching
│   ├── page_ops.py             # Rotation, duplication, deletion, blank page insertion
│   ├── pdf_exporter.py         # Lossless PDF compilation & thumbnail generation
│   ├── sample_doc.py           # Multi-page sample invoice/proposal generator
│   └── text_editor.py          # In-place text replacement, alignment & repositioning
└── static/
    ├── index.html              # Modern, responsive single-page editor interface
    ├── styles.css              # Dark/light theme styles, zero-offset inline box, guides
    └── scripts.js              # State manager, canvas renderer, magnetic snapping logic
```

---

## 🚀 Cloud Deployment Guide

PDF Studio Pro is built from the ground up for zero-downtime, zero-configuration cloud hosting.

### Cloud-Native Safeguards
- **Dynamic Port Assignment**: Reads `PORT` from environment variables (`os.environ.get("PORT", 8000)`) and binds to `0.0.0.0`.
- **Automated Memory Garbage Collection**: Active session tracker auto-prunes documents older than 2 hours or when memory thresholds are met, preventing OOM spikes on free/micro tier instances.
- **50MB Upload Guard**: Safely catches and rejects oversized payloads before they consume memory.
- **Health Check Endpoint**: Built-in `GET /api/health` responds with uptime status for container orchestrators.



## 💻 Local Quick Start

### Prerequisites
- Python 3.10+ installed
- Git

### 1. Clone & Set Up Virtual Environment

```bash
# Clone repository
git clone https://github.com/lalkesh-ds/local_pdf_text_editor.git
cd local_pdf_text_editor

# Create virtual environment
python -m venv myenv

# Activate virtual environment
# Windows:
.\myenv\Scripts\activate
# macOS / Linux:
source myenv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Application

```bash
# Run with live reload
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

On Windows, you can simply double-click **`run.bat`**.

Open your browser at **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.

---

## 🧪 Automated Testing

PDF Studio Pro includes a comprehensive automated integration test suite covering the entire API lifecycle:

```powershell
# Run the test suite
.\myenv\Scripts\python.exe test_app_integration.py
```

### Test Coverage Breakdown:
1. `Test 1`: Sample PDF document generation
2. `Test 2`: High-DPI page rendering & text span coordinate extraction
3. `Test 3`: Thumbnail generation
4. `Test 4`: In-place text editing with font, style, and color matching
5. `Test 5`: Custom text insertion with ($x, y$) coordinate placement
6. `Test 6`: Whiteout & underlying vector glyph redaction
7. `Test 7`: Semi-transparent highlight annotations
8. `Test 8`: Vector shapes (Rectangles, Circles, Directional Arrows)
9. `Test 9`: Freehand ink pen strokes
10. `Test 10`: Signature placement with custom dimensions
11. `Test 11`: Page operations (Rotate 90°, Duplicate, Insert Blank)
12. `Test 12`: Document-wide find & replace
13. `Test 13`: Non-destructive session undo/redo
14. `Test 14`: Clean vector PDF compilation and export

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service liveness healthcheck |
| `POST` | `/api/upload` | Upload PDF file (multipart form data, max 50MB) |
| `POST` | `/api/load-sample` | Generate & load instant multi-page sample document |
| `GET` | `/api/page/{id}/{num}` | Render page image and extract text span coordinates |
| `GET` | `/api/thumbnails/{id}` | Generate thumbnails for all document pages |
| `POST` | `/api/edit-text` | Edit text in-place, reposition ($x,y$), or adjust alignment |
| `POST` | `/api/add-text` | Insert new text element at specific coordinates |
| `POST` | `/api/delete-text` | Redact and erase text span |
| `POST` | `/api/annotate` | Apply whiteout, highlight, shape, or freehand drawing |
| `POST` | `/api/add-image` | Insert signature stamp or image with coordinates |
| `POST` | `/api/page-op` | Execute page rotation, duplication, deletion, or insertion |
| `POST` | `/api/find-replace`| Find and replace text occurrences document-wide |
| `POST` | `/api/undo` | Revert to previous document state |
| `POST` | `/api/redo` | Fast-forward to next document state |
| `GET` | `/api/export/{id}` | Download clean, compiled vector PDF |

---

## 🔒 Security & Privacy

- **No Remote Telemetry**: Zero external tracking, data analytics, or cloud font callouts on private documents.
- **Isolated Memory Sessions**: Documents are kept in ephemeral memory sessions and automatically cleared upon session expiry.
- **Lossless Redactions**: Text obscured by redactions is stripped from the vector stream, preventing reverse-engineering from raw PDF viewers.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). You are free to use this software for personal use.