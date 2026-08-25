# Local PDF Text Editor

**Edit text directly inside a PDF — click a span, retype it, add new text, and export a clean copy. 100% local, no uploads, no accounts.**

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Backend](https://img.shields.io/badge/backend-FastAPI-009688.svg)
![PDF Engine](https://img.shields.io/badge/pdf%20engine-PyMuPDF-orange.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Local Only](https://img.shields.io/badge/data-100%25%20local-brightgreen.svg)

Local PDF Text Editor is a self-hosted, browser-based tool for making direct text edits to a PDF. It runs entirely on `localhost`: there's no upload step, no account, no database, and no telemetry — your files never leave your machine.

---

## Table of Contents

- [Key Features](#key-features)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Usage Guide](#usage-guide)
- [Supported PDF Types](#supported-pdf-types)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Privacy & Data Handling](#privacy--data-handling)
- [Extending This Project](#extending-this-project)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Key Features

**Viewing**
- Upload a PDF and page through it (previous/next, jump-to-page, zoom)
- Pages with no extractable text (typically scans) are flagged automatically

**Editing**
- Click any text span to select it and see its current text, font, size, and style
- Replace text in place — position, approximate font family/weight, size, color, and rotation all carry over automatically
- Automatic shrink-to-fit (down to 6pt) if your replacement text runs long, with an explicit warning rather than a broken layout if it still doesn't fit
- **Add Text** mode: click anywhere to drop in new text, with controls for size, color, bold, and italic
- Session-level undo/redo

**Export**
- One-click export to a new file (`yourfile_edited.pdf`) — your original upload is never modified
- Text removal uses real PDF redaction, not a rectangle painted over the old text
- Existing images, vector graphics, and untouched text are preserved as real PDF content, not flattened into a picture

## Architecture

| Layer | Technology | Responsibility |
|-------|-----------|-----------------|
| **Backend** | FastAPI + [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) | Opens the PDF, extracts each text span's position/font/size/color, applies redaction-based edits, and renders the exported file |
| **Frontend** | HTML, CSS, vanilla JavaScript | Displays each page as an image and overlays invisible clickable regions exactly over the real text, so a click maps precisely to the span beneath it |

**Why not Streamlit?** Streamlit has no reliable way to return the exact pixel/point coordinates of a click on a rendered image, and this editor depends on that precision to match a click to the right text span and place new text exactly where you clicked. A small FastAPI + HTML/JS stack keeps that accuracy without pulling in a heavier framework.

## Getting Started

### Prerequisites

- Python 3.11
- pip (installed with Python)
- Windows 10/11, macOS, or Linux

### Installation

<details>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell refuses to run the activation script, run this once as your normal user (not an administrator), then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

</details>

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

</details>

### Running the App

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in your browser. To stop the server, return to the terminal and press `Ctrl+C`.

## Usage Guide

1. **Upload** a PDF from the start screen.
2. The first page renders on the left, with invisible clickable regions positioned exactly over each text span.
3. **Click existing text** to open it in the side panel, edit the text, and click **Save Change**. The server redacts the original span and inserts your new text using the original position, matched font, size, and color.
4. **Click "＋ Add Text"**, then click anywhere on the page to place new text. Set its size, color, and style, then click **Place Text**.
5. Step through your edits with **Undo / Redo**.
6. Click **Export Edited PDF** to download `yourfile_edited.pdf`. Your original upload is left untouched.

## Supported PDF Types

| Type | Support |
|------|---------|
| Standard text PDFs (Word, Google Docs, LaTeX, "Print to PDF") | ✅ Fully supported |
| Multi-page documents, mixed fonts/sizes/colors, bold/italic | ✅ Fully supported |
| Complex layouts — multi-column, dense tables, text over images | ⚠️ Editable per-span; review results carefully |
| Scanned or image-only PDFs | ❌ No extractable text layer (OCR is out of scope) |
| Text converted to vector outlines/curves | ❌ No longer "real" text, so nothing to select |

## Limitations

- **Fonts are approximated, not reused exactly.** Embedded/subsetted PDF fonts generally can't be reused for freshly-typeset text, so every font is mapped to the closest of 14 standard fonts (Helvetica, Times, and Courier, each in regular/bold/italic/bold-italic). Visually close, but not pixel-perfect.
- **Background matching is a best-effort sample**, not content-aware reconstruction. Solid-color backgrounds (including light colors) match well; gradients, patterns, and text sitting on an image may not reconstruct perfectly, since the edited area is covered with the nearest sampled color.
- **Editing happens span-by-span**, using PyMuPDF's own text segmentation. Curved text, text converted to vector outlines, and unusual multi-column or table layouts may not be cleanly selectable.
- **Scanned/image-only pages aren't editable** — there's no extractable text layer, and OCR is deliberately not part of this tool. Such pages are flagged in the viewer.
- **Undo/redo is per-session and in-memory only.** Closing the app clears history; nothing is auto-saved.
- **On-screen rendering uses page images** (for simple, offline-friendly display), but the **exported file is a real vector PDF** — existing images, vector graphics, and unedited text stay intact rather than being flattened.

## Troubleshooting

<details>
<summary><code>pip install</code> fails on PyMuPDF</summary>

Confirm you're on Python 3.11 (`python --version`) and that pip is current (`python -m pip install --upgrade pip`). PyMuPDF ships prebuilt wheels for Windows, macOS, and Linux, so a compiler shouldn't be needed.

</details>

<details>
<summary>Port already in use</summary>

Start the app on a different port, e.g. `uvicorn app:app --host 127.0.0.1 --port 8010`, and browse to `http://127.0.0.1:8010` instead.

</details>

<details>
<summary>"This PDF is password-protected"</summary>

Remove the password with another tool first — this editor doesn't attempt to crack or manage PDF passwords.

</details>

<details>
<summary>My replacement text got shrunk a lot</summary>

Shorten the text or accept the smaller font size. The app will warn you rather than silently overflow into surrounding content.

</details>

<details>
<summary>A page shows a "scanned or image-based" warning</summary>

That page has no extractable text layer (common for scans), so there's nothing for click-to-edit to select on it.

</details>

<details>
<summary>The browser shows a blank page</summary>

Check that the terminal shows `Uvicorn running on http://127.0.0.1:8000` with no errors, and that you're browsing to that exact address (not `0.0.0.0`).

</details>

## Project Structure

```text
local_pdf_text_editor/
│
├── app.py                   # FastAPI app: sessions + REST endpoints
├── requirements.txt
├── README.md
│
├── pdf_editor/
│   ├── __init__.py
│   ├── pdf_loader.py        # Validate & open PDFs, page dimensions
│   ├── text_extractor.py    # Extract text spans (position/font/color)
│   ├── text_editor.py       # Replace/add text, font fitting, redaction
│   ├── font_matcher.py      # Map PDF fonts to Base14 fallback fonts
│   ├── pdf_exporter.py      # Render page PNGs, export final PDF bytes
│   └── edit_history.py      # In-memory undo/redo (byte snapshots)
│
├── static/
│   ├── index.html
│   ├── styles.css
│   └── scripts.js           # Click-to-edit overlay, add-text, export
│
└── temp/                    # Reserved for local scratch use if needed
    └── .gitkeep
```

## Privacy & Data Handling

> Nothing leaves your machine. There's no upload step, no account, no database, and no telemetry.

- All processing happens in a local FastAPI server on `localhost`
- No file is ever sent to an external service
- No accounts, sign-ins, or usage tracking
- Undo/redo history lives in memory for the current session only and is discarded when the app closes

## Extending This Project

The backend is split into small, single-purpose modules (`pdf_loader`, `text_extractor`, `text_editor`, `font_matcher`, `pdf_exporter`, `edit_history`), so it's straightforward to adapt — for example, adding an OCR fallback for scanned pages, supporting additional font families, or wiring in a different export format. Fork it and adjust it for your own workflow.

## License

[MIT]

## Acknowledgments

- [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF parsing, rendering, and editing
- [FastAPI](https://fastapi.tiangolo.com/) for the backend server