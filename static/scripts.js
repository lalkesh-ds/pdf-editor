/* Local PDF Text Editor - frontend logic.
 *
 * The backend renders each page to a PNG (for accurate, simple display)
 * and separately returns every editable text span's bounding box in PDF
 * point coordinates. This script scales those boxes into on-screen
 * pixel coordinates to build a transparent, clickable overlay on top of
 * the image - that overlay is what the user actually interacts with.
 * Nothing about the overlay is ever written into the exported PDF; only
 * the real fitz edits applied on the server are.
 */

const state = {
  sessionId: null,
  filename: null,
  pageNum: 0,
  pageCount: 1,
  zoom: 1.5,
  pageWidthPt: 0,
  pageHeightPt: 0,
  imageWidthPx: 0,
  imageHeightPx: 0,
  spans: [],
  selectedSpanId: null,
  originalFontSize: null,
  fontSizeModified: false,
  addMode: false,
  pendingAddPoint: null, // {x, y} in PDF points
};

const el = (id) => document.getElementById(id);

function logStatus(message, isError = false) {
  const log = el("status-log");
  const line = document.createElement("div");
  line.className = "log-line" + (isError ? " log-error" : "");
  const time = new Date().toLocaleTimeString();
  line.textContent = `[${time}] ${message}`;
  log.prepend(line);
}

async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ---------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------
el("file-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  el("upload-error").textContent = "";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await apiFetch("/api/upload", { method: "POST", body: formData });
    state.sessionId = data.session_id;
    state.filename = data.filename;
    state.pageCount = data.page_count;
    state.pageNum = 0;

    el("upload-screen").classList.add("hidden");
    el("editor-screen").classList.remove("hidden");
    el("file-info").textContent = `${data.filename} — ${data.page_count} page(s)`;
    el("page-count").textContent = data.page_count;
    el("page-input").max = data.page_count;

    await loadPage(0);
    logStatus(`Loaded ${data.filename}`);
  } catch (err) {
    el("upload-error").textContent = err.message;
  }
});

// ---------------------------------------------------------------------
// Page loading & rendering
// ---------------------------------------------------------------------
async function loadPage(pageNum) {
  const data = await apiFetch(
    `/api/page/${state.sessionId}/${pageNum}?zoom=${state.zoom}`
  );
  applyPagePayload(data);
}

function applyPagePayload(data) {
  state.pageNum = data.page_num;
  state.pageCount = data.page_count;
  state.pageWidthPt = data.page_width;
  state.pageHeightPt = data.page_height;
  state.imageWidthPx = data.image_width;
  state.imageHeightPx = data.image_height;
  state.spans = data.spans;
  state.selectedSpanId = null;

  const img = el("page-image");
  img.src = `data:image/png;base64,${data.image_base64}`;
  img.width = data.image_width;
  img.height = data.image_height;

  el("page-input").value = data.page_num + 1;
  el("page-count").textContent = data.page_count;
  el("zoom-level").textContent = `${Math.round(data.zoom * 100)}%`;

  el("scanned-warning").classList.toggle("hidden", !data.is_scanned);

  if (data.warning) {
    const warnEl = el("edit-warning");
    warnEl.textContent = data.warning;
    warnEl.classList.remove("hidden");
  } else {
    el("edit-warning").classList.add("hidden");
  }

  closeEditPanel();
  closeAddPanel();
  renderOverlay();
  updateNavButtons();
}

function scaleFactor() {
  // pixels per PDF point
  return state.imageWidthPx / state.pageWidthPt;
}

function renderOverlay() {
  const overlay = el("overlay-layer");
  overlay.innerHTML = "";
  const scale = scaleFactor();

  for (const span of state.spans) {
    const [x0, y0, x1, y1] = span.bbox;
    const div = document.createElement("div");
    div.className = "text-span";
    div.style.left = `${x0 * scale}px`;
    div.style.top = `${y0 * scale}px`;
    div.style.width = `${(x1 - x0) * scale}px`;
    div.style.height = `${(y1 - y0) * scale}px`;
    div.title = span.text;
    div.dataset.spanId = span.id;
    div.addEventListener("click", (e) => {
      e.stopPropagation();
      if (state.addMode) return;
      selectSpan(span);
    });
    overlay.appendChild(div);
  }
}

function updateNavButtons() {
  el("prev-page").disabled = state.pageNum <= 0;
  el("next-page").disabled = state.pageNum >= state.pageCount - 1;
}

// ---------------------------------------------------------------------
// Navigation & zoom
// ---------------------------------------------------------------------
el("prev-page").addEventListener("click", () => {
  if (state.pageNum > 0) loadPage(state.pageNum - 1);
});
el("next-page").addEventListener("click", () => {
  if (state.pageNum < state.pageCount - 1) loadPage(state.pageNum + 1);
});
el("page-input").addEventListener("change", (e) => {
  const n = parseInt(e.target.value, 10) - 1;
  if (!isNaN(n) && n >= 0 && n < state.pageCount) loadPage(n);
});
el("zoom-in").addEventListener("click", () => {
  state.zoom = Math.min(state.zoom + 0.25, 4.0);
  loadPage(state.pageNum);
});
el("zoom-out").addEventListener("click", () => {
  state.zoom = Math.max(state.zoom - 0.25, 0.5);
  loadPage(state.pageNum);
});

// ---------------------------------------------------------------------
// Edit existing text
// ---------------------------------------------------------------------
function selectSpan(span) {
  state.selectedSpanId = span.id;
  document.querySelectorAll(".text-span").forEach((d) => d.classList.remove("selected"));
  const chosen = document.querySelector(`.text-span[data-span-id="${CSS.escape(span.id)}"]`);
  if (chosen) chosen.classList.add("selected");

  el("select-hint").classList.add("hidden");
  el("add-panel").classList.add("hidden");
  el("edit-panel").classList.remove("hidden");
  el("current-text").textContent = span.text;
  el("replacement-text").value = span.text;
  el("span-meta").textContent =
    `Font: ${span.font || "unknown"} · Size: ${span.size}pt` +
    (span.bold ? " · Bold" : "") + (span.italic ? " · Italic" : "");

  // Font size defaults to the original extracted size and is treated as
  // "unmodified" until the user explicitly touches the control - that
  // distinction is what tells the backend whether to auto-fit (only
  // shrinking if truly necessary) or to use the user's exact chosen size.
  state.originalFontSize = span.size;
  state.fontSizeModified = false;
  el("font-size-input").value = span.size;

  el("replacement-text").focus();
}

function closeEditPanel() {
  el("edit-panel").classList.add("hidden");
  el("select-hint").classList.toggle("hidden", state.addMode);
  document.querySelectorAll(".text-span").forEach((d) => d.classList.remove("selected"));
}

el("cancel-edit-btn").addEventListener("click", closeEditPanel);

el("font-size-minus").addEventListener("click", () => {
  const input = el("font-size-input");
  const current = parseFloat(input.value) || state.originalFontSize || 12;
  input.value = Math.max(0.5, Math.round((current - 0.5) * 10) / 10);
  state.fontSizeModified = true;
});

el("font-size-plus").addEventListener("click", () => {
  const input = el("font-size-input");
  const current = parseFloat(input.value) || state.originalFontSize || 12;
  input.value = Math.round((current + 0.5) * 10) / 10;
  state.fontSizeModified = true;
});

el("font-size-input").addEventListener("input", () => {
  state.fontSizeModified = true;
});

el("font-size-reset").addEventListener("click", () => {
  if (state.originalFontSize != null) {
    el("font-size-input").value = state.originalFontSize;
  }
  state.fontSizeModified = false;
});

el("save-edit-btn").addEventListener("click", async () => {
  if (!state.selectedSpanId) return;
  const newText = el("replacement-text").value;

  // Only send an explicit font_size when the user actually touched the
  // control - otherwise the backend keeps the original size by default
  // and only shrinks it if the text truly doesn't fit the available space.
  const fontSize = state.fontSizeModified
    ? parseFloat(el("font-size-input").value) || state.originalFontSize
    : null;

  el("save-edit-btn").disabled = true;
  try {
    const data = await apiFetch("/api/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        page_num: state.pageNum,
        span_id: state.selectedSpanId,
        new_text: newText,
        font_size: fontSize,
      }),
    });
    applyPagePayload(data);
    updateHistoryButtons();
    logStatus(
      data.used_font_size
        ? `Text updated (${data.used_font_size}pt).`
        : "Text updated."
    );
  } catch (err) {
    logStatus(`Edit failed: ${err.message}`, true);
  } finally {
    el("save-edit-btn").disabled = false;
  }
});

// ---------------------------------------------------------------------
// Add new text
// ---------------------------------------------------------------------
el("add-text-mode").addEventListener("click", () => {
  state.addMode = !state.addMode;
  el("add-text-mode").classList.toggle("active", state.addMode);
  el("page-container").classList.toggle("add-mode", state.addMode);
  closeEditPanel();
  if (state.addMode) {
    el("select-hint").textContent = "Click anywhere on the page to place new text.";
    el("select-hint").classList.remove("hidden");
  } else {
    el("select-hint").textContent =
      "Click on any existing text in the page to edit it, or use \"Add Text\" to place new text.";
    closeAddPanel();
  }
});

el("page-container").addEventListener("click", (e) => {
  if (!state.addMode) return;
  const rect = el("page-image").getBoundingClientRect();
  const clickXPx = e.clientX - rect.left;
  const clickYPx = e.clientY - rect.top;
  const scale = scaleFactor();
  const pdfX = clickXPx / scale;
  const pdfY = clickYPx / scale;

  state.pendingAddPoint = { x: pdfX, y: pdfY };
  el("select-hint").classList.add("hidden");
  el("add-panel").classList.remove("hidden");
  el("add-text-input").value = "";
  el("add-text-input").focus();
  el("save-add-btn").disabled = false;
});

function closeAddPanel() {
  el("add-panel").classList.add("hidden");
  state.pendingAddPoint = null;
}

el("cancel-add-btn").addEventListener("click", () => {
  closeAddPanel();
  if (state.addMode) {
    el("select-hint").classList.remove("hidden");
  }
});

el("save-add-btn").addEventListener("click", async () => {
  if (!state.pendingAddPoint) return;
  const text = el("add-text-input").value;
  if (!text.trim()) return;

  el("save-add-btn").disabled = true;
  try {
    const data = await apiFetch("/api/add_text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        page_num: state.pageNum,
        x: state.pendingAddPoint.x,
        // baseline expected by fitz.insert_text - use the y coordinate
        // roughly as the text's bottom edge so it appears where clicked.
        y: state.pendingAddPoint.y,
        text: text,
        fontsize: parseFloat(el("add-font-size").value) || 12,
        color: el("add-color").value,
        bold: el("add-bold").checked,
        italic: el("add-italic").checked,
      }),
    });
    applyPagePayload(data);
    updateHistoryButtons();
    logStatus("Text added.");
    // Stay in add mode so the user can place multiple pieces of text.
    if (state.addMode) {
      el("select-hint").classList.remove("hidden");
    }
  } catch (err) {
    logStatus(`Add text failed: ${err.message}`, true);
  } finally {
    el("save-add-btn").disabled = false;
  }
});

// ---------------------------------------------------------------------
// Undo / redo
// ---------------------------------------------------------------------
function updateHistoryButtons() {
  // Any new edit pushes onto the undo stack and clears the redo stack
  // server-side (see edit_history.py), so mirror that here.
  el("undo-btn").disabled = false;
  el("redo-btn").disabled = true;
}

el("undo-btn").addEventListener("click", async () => {
  try {
    const data = await apiFetch("/api/undo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        page_num: state.pageNum,
        zoom: state.zoom,
      }),
    });
    applyPagePayload(data);
    el("redo-btn").disabled = false;
    logStatus("Undid last change.");
  } catch (err) {
    logStatus(`Undo failed: ${err.message}`, true);
  }
});

el("redo-btn").addEventListener("click", async () => {
  try {
    const data = await apiFetch("/api/redo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        page_num: state.pageNum,
        zoom: state.zoom,
      }),
    });
    applyPagePayload(data);
    logStatus("Redid change.");
  } catch (err) {
    logStatus(`Redo failed: ${err.message}`, true);
  }
});

// ---------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------
el("export-btn").addEventListener("click", () => {
  if (!state.sessionId) return;
  window.location.href = `/api/export/${state.sessionId}`;
  logStatus("Export started - check your downloads folder.");
});
