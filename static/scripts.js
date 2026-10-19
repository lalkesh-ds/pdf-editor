/**
 * PDF Studio Pro - Advanced Web & Cloud PDF Editor
 * Complete WYSIWYG in-place text editing, signatures, whiteout, annotations, shapes,
 * page organization, and find/replace.
 */

// Global State
const appState = {
  sessionId: null,
  filename: "document.pdf",
  pageNum: 0,
  pageCount: 1,
  zoom: 1.5,
  pageWidthPt: 595,
  pageHeightPt: 842,
  imageWidthPx: 892,
  imageHeightPx: 1263,
  rotation: 0,
  spans: [],

  // Active Tool Mode: 'text', 'forms', 'image', 'sign', 'whiteout', 'annotate', 'shapes', 'find_replace'
  activeTool: 'text',

  // Inline Text Editor State
  editingSpan: null,
  isNewText: false,
  newTextPt: null, // { x, y } in PDF points
  activeTextStyle: {
    fontFamily: 'sans',
    fontSize: 12,
    bold: false,
    italic: false,
    color: '#000000',
    sizeModified: false,
  },

  // Tool Specific Settings
  toolSettings: {
    whiteout: { mode: 'white', fill: '#ffffff', redact: true },
    annotate: { type: 'highlight', color: '#ffe066', opacity: 0.45, penWidth: 2.5 },
    shapes: { type: 'rect', stroke: '#000000', fill: null, width: 2.0 },
    forms: { type: 'textfield' },
  },

  // Interactive Drawing on Canvas
  drawState: {
    isDrawing: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    points: [], // for freehand
  },

  // Transform Box (Images & Signatures)
  transform: {
    active: false,
    imgData: null,
    x: 100, // PDF points
    y: 100,
    width: 160,
    height: 60,
    isDragging: false,
    isResizing: false,
    activeHandle: null,
    dragStartX: 0,
    dragStartY: 0,
    initialBox: null,
  },

  // Signature Modal State
  sigPad: {
    canvas: null,
    ctx: null,
    isDrawing: false,
    inkColor: '#000000',
    lastX: 0,
    lastY: 0,
    hasSignature: false,
  },
  sigTypeFont: 'Great Vibes',
  uploadedSigData: null,

  // UI state
  thumbnailsOpen: true,
};

// Utility helper
const $ = (id) => document.getElementById(id);

function showToast(message, type = 'info') {
  const container = $('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  let icon = 'ℹ️';
  if (type === 'success') icon = '✓';
  if (type === 'error') icon = '⚠️';
  toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return await res.json();
  } catch (err) {
    showToast(err.message, 'error');
    throw err;
  }
}

function scaleFactor() {
  return appState.imageWidthPx / appState.pageWidthPt;
}

function pdfToScreen(x, y) {
  const s = scaleFactor();
  return { x: x * s, y: y * s };
}

function screenToPdf(px, py) {
  const s = scaleFactor();
  return { x: px / s, y: py / s };
}

// ==========================================================================
// Initialization & Document Loading
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  initSignaturePad();
  initDrawingCanvas();
});

function initEventListeners() {
  // File Upload
  $('file-input').addEventListener('change', handleFileUpload);
  const dropzone = $('dropzone');
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  // Load Sample Proposal PDF
  $('load-sample-btn').addEventListener('click', loadSamplePdf);

  // Topbar Navigation & Zoom
  $('prev-page-btn').addEventListener('click', () => { if (appState.pageNum > 0) goToPage(appState.pageNum - 1); });
  $('next-page-btn').addEventListener('click', () => { if (appState.pageNum < appState.pageCount - 1) goToPage(appState.pageNum + 1); });
  $('page-num-input').addEventListener('change', (e) => {
    const p = parseInt(e.target.value, 10) - 1;
    if (!isNaN(p) && p >= 0 && p < appState.pageCount) goToPage(p);
  });
  $('zoom-in-btn').addEventListener('click', () => setZoom(Math.min(appState.zoom + 0.25, 3.5)));
  $('zoom-out-btn').addEventListener('click', () => setZoom(Math.max(appState.zoom - 0.25, 0.5)));
  $('zoom-fit-btn').addEventListener('click', fitPageWidth);

  // Undo / Redo / Export
  $('undo-btn').addEventListener('click', performUndo);
  $('redo-btn').addEventListener('click', performRedo);
  $('export-btn').addEventListener('click', exportPdf);
  $('new-doc-btn').addEventListener('click', () => {
    if (confirm('Open a new PDF? Any unsaved session will remain local.')) {
      $('editor-screen').classList.add('hidden');
      $('upload-screen').classList.remove('hidden');
    }
  });

  // Toggle Left Thumbnails Drawer
  $('toggle-thumbs-btn').addEventListener('click', toggleThumbnailsDrawer);
  $('add-blank-page-top').addEventListener('click', () => insertBlankPage());

  // Tool Ribbon Buttons
  document.querySelectorAll('.ribbon-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tool = btn.dataset.tool;
      selectTool(tool);
    });
  });

  // Floating Context Toolbar Actions
  $('fmt-size-down').addEventListener('click', () => adjustFontSize(-0.5));
  $('fmt-size-up').addEventListener('click', () => adjustFontSize(0.5));
  $('fmt-size-input').addEventListener('input', (e) => {
    appState.activeTextStyle.fontSize = parseFloat(e.target.value) || 12;
    appState.activeTextStyle.sizeModified = true;
    updateInlineInputVisuals();
  });
  $('fmt-font-family').addEventListener('change', (e) => {
    appState.activeTextStyle.fontFamily = e.target.value;
    updateInlineInputVisuals();
  });
  $('fmt-bold').addEventListener('click', () => {
    appState.activeTextStyle.bold = !appState.activeTextStyle.bold;
    $('fmt-bold').classList.toggle('active', appState.activeTextStyle.bold);
    updateInlineInputVisuals();
  });
  $('fmt-italic').addEventListener('click', () => {
    appState.activeTextStyle.italic = !appState.activeTextStyle.italic;
    $('fmt-italic').classList.toggle('active', appState.activeTextStyle.italic);
    updateInlineInputVisuals();
  });
  $('fmt-color').addEventListener('input', (e) => {
    appState.activeTextStyle.color = e.target.value;
    $('fmt-color-indicator').style.background = e.target.value;
    updateInlineInputVisuals();
  });
  $('fmt-apply').addEventListener('click', commitInlineEdit);
  // Text Alignment Controls: Auto-commits immediately on click!
  document.querySelectorAll('.fmt-align').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.fmt-align').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      appState.activeTextStyle.align = btn.dataset.align;
      $('inline-input').style.textAlign = btn.dataset.align;
      // Auto-commit alignment immediately without requiring Done click
      if (appState.editingSpan || appState.isNewText) {
        await commitInlineEdit();
      }
    });
  });

  // Initialize Text Drag & Snap Handler
  initTextDragAndSnap();

  // Inline input keyboard shortcuts
  const inlineInput = $('inline-input');
  inlineInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      commitInlineEdit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeInlineEditor();
    }
  });

  // Page canvas click for Add Text or deselecting
  $('page-wrapper').addEventListener('click', handlePageWrapperClick);

  // Transform Box (Dragging & Resizing Images/Signatures)
  initTransformBoxEvents();

  // Signature Modal Tabs & Handlers
  initSignatureModal();

  // Find & Replace Modal Handlers
  initFindReplaceModal();

  // Hidden Image File Input
  $('image-tool-input').addEventListener('change', handleImageToolFile);

  // Keyboard Shortcuts (Global)
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      if (!e.shiftKey) performUndo();
      else performRedo();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
      e.preventDefault();
      performRedo();
    } else if (e.key === 'Escape') {
      closeInlineEditor();
      cancelTransformBox();
    }
  });
}

// ==========================================================================
// Document Loading & Page Rendering
// ==========================================================================

async function handleFileUpload(e) {
  const file = e.target.files[0];
  if (file) uploadFile(file);
}

async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showToast('Please select a valid PDF file.', 'error');
    return;
  }
  const formData = new FormData();
  formData.append('file', file);

  try {
    const data = await apiFetch('/api/upload', { method: 'POST', body: formData });
    setupLoadedSession(data);
    showToast(`Loaded ${data.filename} (${data.page_count} pages)`, 'success');
  } catch (err) {
    $('upload-error').textContent = err.message;
  }
}

async function loadSamplePdf() {
  try {
    const data = await apiFetch('/api/sample');
    setupLoadedSession(data);
    showToast('Loaded interactive sample document!', 'success');
  } catch (err) {
    showToast('Could not load sample PDF: ' + err.message, 'error');
  }
}

function setupLoadedSession(data) {
  appState.sessionId = data.session_id;
  appState.filename = data.filename;
  appState.pageCount = data.page_count;
  appState.pageNum = 0;

  $('doc-title').textContent = data.filename;
  $('doc-title').classList.remove('hidden');
  $('upload-screen').classList.add('hidden');
  $('editor-screen').classList.remove('hidden');

  goToPage(0);
  loadThumbnails();
}

async function goToPage(pageNum) {
  if (!appState.sessionId) return;
  closeInlineEditor();
  cancelTransformBox();

  try {
    const data = await apiFetch(`/api/page/${appState.sessionId}/${pageNum}?zoom=${appState.zoom}`);
    applyPagePayload(data);
  } catch (err) {
    console.error('Page load error:', err);
  }
}

function applyPagePayload(data) {
  appState.pageNum = data.page_num;
  appState.pageCount = data.page_count;
  appState.pageWidthPt = data.page_width;
  appState.pageHeightPt = data.page_height;
  appState.imageWidthPx = data.image_width;
  appState.imageHeightPx = data.image_height;
  appState.rotation = data.rotation || 0;
  appState.spans = data.spans;

  // Set rendered image
  const img = $('page-image');
  img.src = `data:image/png;base64,${data.image_base64}`;
  img.style.width = `${data.image_width}px`;
  img.style.height = `${data.image_height}px`;

  // Size page-wrapper and drawing canvas to match
  const wrapper = $('page-wrapper');
  wrapper.style.width = `${data.image_width}px`;
  wrapper.style.height = `${data.image_height}px`;

  const canvas = $('drawing-canvas');
  canvas.width = data.image_width;
  canvas.height = data.image_height;
  canvas.style.width = `${data.image_width}px`;
  canvas.style.height = `${data.image_height}px`;

  // Controls update
  $('page-num-input').value = data.page_num + 1;
  $('page-num-input').max = data.page_count;
  $('page-count-val').textContent = data.page_count;
  $('zoom-val-text').textContent = `${Math.round(data.zoom * 100)}%`;

  $('prev-page-btn').disabled = data.page_num <= 0;
  $('next-page-btn').disabled = data.page_num >= data.page_count - 1;

  $('scanned-banner').classList.toggle('hidden', !data.is_scanned);

  if (data.warning) {
    const eb = $('edit-banner');
    eb.textContent = data.warning;
    eb.classList.remove('hidden');
    setTimeout(() => eb.classList.add('hidden'), 6000);
  } else {
    $('edit-banner').classList.add('hidden');
  }

  renderSpansOverlay();
  highlightActiveThumbnail();
}

function renderSpansOverlay() {
  const overlay = $('overlay-layer');
  overlay.innerHTML = '';
  const scale = scaleFactor();

  // If active tool is not 'text', overlay should be non-interfering
  overlay.style.pointerEvents = (appState.activeTool === 'text') ? 'auto' : 'none';

  for (const span of appState.spans) {
    const [x0, y0, x1, y1] = span.bbox;
    const div = document.createElement('div');
    div.className = 'text-span';
    div.style.left = `${x0 * scale}px`;
    div.style.top = `${y0 * scale}px`;
    div.style.width = `${Math.max((x1 - x0) * scale, 6)}px`;
    div.style.height = `${Math.max((y1 - y0) * scale, 8)}px`;
    div.title = span.text;
    div.dataset.spanId = span.id;

    div.addEventListener('click', (e) => {
      e.stopPropagation();
      if (appState.activeTool === 'text') {
        openInlineEditorForSpan(span);
      }
    });

    overlay.appendChild(div);
  }
}

function setZoom(newZoom) {
  appState.zoom = Math.round(newZoom * 100) / 100;
  goToPage(appState.pageNum);
}

function fitPageWidth() {
  const containerWidth = $('canvas-scroll').clientWidth - 64;
  if (containerWidth > 100 && appState.pageWidthPt > 0) {
    const targetZoom = containerWidth / appState.pageWidthPt;
    setZoom(Math.max(0.5, Math.min(targetZoom, 2.8)));
  }
}

// ==========================================================================
// Tool Ribbon Switching
// ==========================================================================

function selectTool(toolName) {
  if (toolName === 'find_replace') {
    openFindReplaceModal();
    return;
  }

  appState.activeTool = toolName;
  closeInlineEditor();
  cancelTransformBox();

  document.querySelectorAll('.ribbon-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tool === toolName);
  });

  const drawingCanvas = $('drawing-canvas');
  const overlay = $('overlay-layer');

  // Configure interactions
  if (toolName === 'text') {
    drawingCanvas.classList.remove('active');
    overlay.style.pointerEvents = 'auto';
    renderSubbarText();
  } else if (toolName === 'image') {
    drawingCanvas.classList.remove('active');
    overlay.style.pointerEvents = 'none';
    renderSubbarImage();
    // Trigger image open dialog
    $('image-tool-input').click();
  } else if (toolName === 'sign') {
    drawingCanvas.classList.remove('active');
    overlay.style.pointerEvents = 'none';
    renderSubbarSign();
    openSignatureModal();
  } else if (toolName === 'whiteout') {
    drawingCanvas.classList.add('active');
    overlay.style.pointerEvents = 'none';
    renderSubbarWhiteout();
  } else if (toolName === 'annotate') {
    drawingCanvas.classList.add('active');
    overlay.style.pointerEvents = 'none';
    renderSubbarAnnotate();
  } else if (toolName === 'shapes') {
    drawingCanvas.classList.add('active');
    overlay.style.pointerEvents = 'none';
    renderSubbarShapes();
  } else if (toolName === 'forms') {
    drawingCanvas.classList.remove('active');
    overlay.style.pointerEvents = 'none';
    renderSubbarForms();
  }
}

function renderSubbarText() {
  $('subbar-content').innerHTML = `
    <span class="subbar-hint">Click existing text to edit inline, or click anywhere on empty space to drop new text.</span>
  `;
}

function renderSubbarImage() {
  $('subbar-content').innerHTML = `
    <button class="subbar-btn-pill active" onclick="document.getElementById('image-tool-input').click()">📁 Select Image / Logo</button>
    <span class="subbar-hint">PNG, JPEG, and transparent logos supported. Drag and resize before placing.</span>
  `;
}

function renderSubbarSign() {
  $('subbar-content').innerHTML = `
    <button class="subbar-btn-pill active" onclick="openSignatureModal()">✍️ Create / Pick Signature</button>
    <span class="subbar-hint">Draw, type with cursive font, or upload your signature.</span>
  `;
}

function renderSubbarWhiteout() {
  $('subbar-content').innerHTML = `
    <div class="subbar-ctrl-group">
      <label>Mode:</label>
      <button class="subbar-btn-pill ${appState.toolSettings.whiteout.mode === 'white' ? 'active' : ''}" onclick="setWhiteoutMode('white')">Whiteout (Clean Background)</button>
      <button class="subbar-btn-pill ${appState.toolSettings.whiteout.mode === 'black' ? 'active' : ''}" onclick="setWhiteoutMode('black')">Black Redaction</button>
    </div>
    <span class="subbar-hint">Click and drag a box over content to erase it permanently.</span>
  `;
}

window.setWhiteoutMode = function(mode) {
  appState.toolSettings.whiteout.mode = mode;
  appState.toolSettings.whiteout.fill = (mode === 'white') ? '#ffffff' : '#000000';
  renderSubbarWhiteout();
};

function renderSubbarAnnotate() {
  const current = appState.toolSettings.annotate;
  $('subbar-content').innerHTML = `
    <div class="subbar-ctrl-group">
      <label>Tool:</label>
      <button class="subbar-btn-pill ${current.type === 'highlight' ? 'active' : ''}" onclick="setAnnotateType('highlight')">Highlight</button>
      <button class="subbar-btn-pill ${current.type === 'pen' ? 'active' : ''}" onclick="setAnnotateType('pen')">Freehand Pen</button>
    </div>
    <div class="subbar-ctrl-group">
      <label>Color:</label>
      <button class="color-chip ${current.color === '#ffe066' ? 'active' : ''}" style="background:#ffe066" onclick="setAnnotateColor('#ffe066')"></button>
      <button class="color-chip ${current.color === '#86efac' ? 'active' : ''}" style="background:#86efac" onclick="setAnnotateColor('#86efac')"></button>
      <button class="color-chip ${current.color === '#93c5fd' ? 'active' : ''}" style="background:#93c5fd" onclick="setAnnotateColor('#93c5fd')"></button>
      <button class="color-chip ${current.color === '#f472b6' ? 'active' : ''}" style="background:#f472b6" onclick="setAnnotateColor('#f472b6')"></button>
    </div>
    <span class="subbar-hint">${current.type === 'highlight' ? 'Drag over text to highlight.' : 'Draw freely with your mouse/pen.'}</span>
  `;
}

window.setAnnotateType = function(type) {
  appState.toolSettings.annotate.type = type;
  renderSubbarAnnotate();
};

window.setAnnotateColor = function(color) {
  appState.toolSettings.annotate.color = color;
  renderSubbarAnnotate();
};

function renderSubbarShapes() {
  const current = appState.toolSettings.shapes;
  $('subbar-content').innerHTML = `
    <div class="subbar-ctrl-group">
      <label>Shape:</label>
      <button class="subbar-btn-pill ${current.type === 'rect' ? 'active' : ''}" onclick="setShapeType('rect')">Rectangle</button>
      <button class="subbar-btn-pill ${current.type === 'circle' ? 'active' : ''}" onclick="setShapeType('circle')">Circle / Ellipse</button>
      <button class="subbar-btn-pill ${current.type === 'line' ? 'active' : ''}" onclick="setShapeType('line')">Line</button>
      <button class="subbar-btn-pill ${current.type === 'arrow' ? 'active' : ''}" onclick="setShapeType('arrow')">Arrow</button>
    </div>
    <div class="subbar-ctrl-group">
      <label>Stroke:</label>
      <input type="color" value="${current.stroke}" onchange="setShapeStroke(this.value)" style="width:24px;height:24px;border:none;border-radius:4px;cursor:pointer;">
    </div>
    <span class="subbar-hint">Click & drag on the document to draw.</span>
  `;
}

window.setShapeType = function(type) {
  appState.toolSettings.shapes.type = type;
  renderSubbarShapes();
};
window.setShapeStroke = function(color) {
  appState.toolSettings.shapes.stroke = color;
};

function renderSubbarForms() {
  $('subbar-content').innerHTML = `
    <div class="subbar-ctrl-group">
      <button class="subbar-btn-pill active" onclick="addCheckmark()">✓ Add Checkmark</button>
      <button class="subbar-btn-pill" onclick="addCrossmark()">✗ Add Cross</button>
    </div>
    <span class="subbar-hint">Click a symbol, then place it anywhere on your form or document.</span>
  `;
}

window.addCheckmark = function() {
  selectTool('text');
  // Drop a checkmark symbol
  appState.isNewText = true;
  appState.newTextPt = { x: 100, y: 150 };
  openInlineEditorForNewText('✓', 16, '#0d47a1');
};

window.addCrossmark = function() {
  selectTool('text');
  appState.isNewText = true;
  appState.newTextPt = { x: 100, y: 150 };
  openInlineEditorForNewText('✗', 16, '#dc2626');
};

// ==========================================================================
// In-Place Inline Text Editing & Drag Repositioning
// ==========================================================================

function initTextDragAndSnap() {
  const handle = $('inline-drag-handle');
  const editor = $('inline-editor');

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();

    const scale = scaleFactor();
    const span = appState.editingSpan;
    const origOriginX = span ? span.origin[0] : (appState.newTextPt ? appState.newTextPt.x : editor.offsetLeft / scale);
    const origOriginY = span ? span.origin[1] : (appState.newTextPt ? appState.newTextPt.y : (editor.offsetTop + editor.offsetHeight * 0.8) / scale);

    appState.textDrag = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      initialLeft: editor.offsetLeft,
      initialTop: editor.offsetTop,
      origOriginX: origOriginX,
      origOriginY: origOriginY,
      moved: false,
      targetPdfX: origOriginX,
      targetPdfY: origOriginY,
    };
  });

  window.addEventListener('mousemove', (e) => {
    if (!appState.textDrag || !appState.textDrag.isDragging) return;
    const td = appState.textDrag;
    const scale = scaleFactor();
    const guidesContainer = $('alignment-guides');
    guidesContainer.innerHTML = '';

    const deltaScreenX = e.clientX - td.startX;
    const deltaScreenY = e.clientY - td.startY;

    let candLeft = td.initialLeft + deltaScreenX;
    let candTop = td.initialTop + deltaScreenY;

    const editorW = editor.offsetWidth;
    const editorH = editor.offsetHeight;
    const editorCenterX = candLeft + (editorW / 2);

    const span = appState.editingSpan;
    const baselineOffsetScreen = span ? (span.origin[1] - span.bbox[1]) * scale : (editorH * 0.8);
    let candBaselineYScreen = candTop + baselineOffsetScreen;

    const SNAP_TOLERANCE = 6; // pixels
    let snappedX = false;
    let snappedY = false;
    let finalOriginX = td.origOriginX + (deltaScreenX / scale);
    let finalOriginY = td.origOriginY + (deltaScreenY / scale);

    // 1. Page Center Snap
    const pageCenterX = appState.imageWidthPx / 2;
    if (Math.abs(editorCenterX - pageCenterX) < SNAP_TOLERANCE) {
      candLeft = pageCenterX - (editorW / 2);
      finalOriginX = screenToPdf(candLeft, 0).x;
      snappedX = true;
      renderGuideLine('vertical', pageCenterX, 'Page Center');
    }

    // 2. Snap with other text spans (Baselines & Columns)
    for (const sp of appState.spans) {
      if (appState.editingSpan && sp.id === appState.editingSpan.id) continue;
      const spBaselineScreen = sp.origin[1] * scale;
      const spLeftScreen = sp.bbox[0] * scale;
      const spRightScreen = sp.bbox[2] * scale;
      const spCenterX = (spLeftScreen + spRightScreen) / 2;

      // Exact Baseline (Row) Snap
      if (!snappedY && Math.abs(candBaselineYScreen - spBaselineScreen) < SNAP_TOLERANCE) {
        candTop = spBaselineScreen - baselineOffsetScreen;
        finalOriginY = sp.origin[1];
        snappedY = true;
        renderGuideLine('horizontal', spBaselineScreen, 'Row Align');
      }

      // Column Snap (Left, Center, Right)
      if (!snappedX) {
        if (Math.abs(candLeft - spLeftScreen) < SNAP_TOLERANCE) {
          candLeft = spLeftScreen;
          finalOriginX = sp.bbox[0];
          snappedX = true;
          renderGuideLine('vertical', spLeftScreen, 'Left Align');
        } else if (Math.abs(editorCenterX - spCenterX) < SNAP_TOLERANCE) {
          candLeft = spCenterX - (editorW / 2);
          finalOriginX = screenToPdf(candLeft, 0).x;
          snappedX = true;
          renderGuideLine('vertical', spCenterX, 'Center Align');
        } else if (Math.abs((candLeft + editorW) - spRightScreen) < SNAP_TOLERANCE) {
          candLeft = spRightScreen - editorW;
          finalOriginX = screenToPdf(candLeft, 0).x;
          snappedX = true;
          renderGuideLine('vertical', spRightScreen, 'Right Align');
        }
      }
    }

    editor.style.left = `${candLeft}px`;
    editor.style.top = `${candTop}px`;
    td.moved = true;
    td.targetPdfX = finalOriginX;
    td.targetPdfY = finalOriginY;

    positionFloatingToolbar(candLeft, candTop);
  });

  window.addEventListener('mouseup', async () => {
    if (appState.textDrag && appState.textDrag.isDragging) {
      const moved = appState.textDrag.moved;
      appState.textDrag.isDragging = false;
      const guidesContainer = $('alignment-guides');
      if (guidesContainer) guidesContainer.innerHTML = '';

      // Auto-place immediately when user drops text! No confirm button needed!
      if (moved) {
        await commitInlineEdit();
      }
    }
  });
}

function renderGuideLine(orientation, coord, label) {
  const container = $('alignment-guides');
  if (!container) return;
  const line = document.createElement('div');
  line.className = `guide-line ${orientation}`;
  if (orientation === 'vertical') {
    line.style.left = `${coord}px`;
  } else {
    line.style.top = `${coord}px`;
  }

  const tag = document.createElement('span');
  tag.className = 'guide-tag';
  tag.textContent = label;
  if (orientation === 'vertical') {
    tag.style.left = `${coord + 4}px`;
    tag.style.top = `16px`;
  } else {
    tag.style.top = `${coord + 4}px`;
    tag.style.left = `16px`;
  }
  container.appendChild(line);
  container.appendChild(tag);
}

function openInlineEditorForSpan(span) {
  appState.editingSpan = span;
  appState.isNewText = false;
  appState.newTextPt = null;
  appState.textDrag = {
    isDragging: false,
    moved: false,
    targetPdfX: span.origin[0],
    targetPdfY: span.origin[1],
  };

  const scale = scaleFactor();
  const [x0, y0, x1, y1] = span.bbox;

  // Auto-detect font family from PDF metadata
  let fam = 'sans';
  const cleanFont = (span.font || '').toLowerCase();
  if (cleanFont.includes('times') || cleanFont.includes('serif') || cleanFont.includes('georgia') || cleanFont.includes('cambria')) {
    fam = 'serif';
  } else if (cleanFont.includes('courier') || cleanFont.includes('mono') || cleanFont.includes('consolas')) {
    fam = 'mono';
  }

  // Exact auto-detection of font size, style, and color from the original text
  appState.activeTextStyle = {
    fontFamily: fam,
    fontSize: span.size, // Exact original font size preserved!
    bold: !!span.bold,
    italic: !!span.italic,
    color: span.color || '#000000',
    align: 'left',
    sizeModified: false,
  };

  const editor = $('inline-editor');
  const input = $('inline-input');

  editor.style.left = `${x0 * scale}px`;
  editor.style.top = `${y0 * scale}px`;
  editor.style.width = `${Math.max((x1 - x0) * scale, 15)}px`;
  editor.style.height = `${Math.max((y1 - y0) * scale, 12)}px`;
  editor.classList.remove('hidden');

  input.textContent = span.text;
  input.style.textAlign = 'left';
  updateInlineInputVisuals();

  positionFloatingToolbar(x0 * scale, y0 * scale);
  syncToolbarControls();

  // Show Auto-matched indicator badge with detected details
  const cleanBadgeName = (span.font || fam).split('+').pop();
  $('fmt-auto-badge').textContent = `Auto: ${cleanBadgeName} (${span.size}pt)`;
  $('fmt-auto-badge').title = `Original detected: ${span.font}, size ${span.size}pt`;

  // Focus and select all
  setTimeout(() => {
    input.focus();
    const range = document.createRange();
    range.selectNodeContents(input);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }, 10);
}

function openInlineEditorForNewText(initialText = '', fontSize = 12, color = '#000000') {
  appState.editingSpan = null;
  appState.isNewText = true;
  appState.textDrag = {
    isDragging: false,
    moved: false,
    targetPdfX: appState.newTextPt.x,
    targetPdfY: appState.newTextPt.y,
  };

  appState.activeTextStyle = {
    fontFamily: 'sans',
    fontSize: fontSize,
    bold: false,
    italic: false,
    color: color,
    align: 'left',
    sizeModified: false,
  };

  const scale = scaleFactor();
  const screenPos = pdfToScreen(appState.newTextPt.x, appState.newTextPt.y);

  const editor = $('inline-editor');
  const input = $('inline-input');

  editor.style.left = `${screenPos.x}px`;
  editor.style.top = `${screenPos.y - (fontSize * scale)}px`;
  editor.style.width = `120px`;
  editor.style.height = `${fontSize * scale * 1.2}px`;
  editor.classList.remove('hidden');

  input.textContent = initialText;
  input.style.textAlign = 'left';
  updateInlineInputVisuals();

  positionFloatingToolbar(screenPos.x, screenPos.y - (fontSize * scale));
  syncToolbarControls();

  $('fmt-auto-badge').textContent = `New Text (${fontSize}pt)`;

  setTimeout(() => input.focus(), 10);
}

function handlePageWrapperClick(e) {
  if (appState.activeTool !== 'text') return;
  // If clicked directly on the page background (not on an existing span or the inline editor)
  if (e.target.id === 'page-image' || e.target.id === 'overlay-layer') {
    if (!appState.editingSpan && !$('inline-editor').classList.contains('hidden')) {
      commitInlineEdit();
      return;
    }
    if (appState.editingSpan && !$('inline-editor').classList.contains('hidden')) {
      commitInlineEdit();
      return;
    }
    const rect = $('page-image').getBoundingClientRect();
    const clickXPx = e.clientX - rect.left;
    const clickYPx = e.clientY - rect.top;
    const pt = screenToPdf(clickXPx, clickYPx);

    appState.newTextPt = pt;
    openInlineEditorForNewText('Type text...', 12, '#000000');
  }
}

function updateInlineInputVisuals() {
  const input = $('inline-input');
  const s = scaleFactor();
  const style = appState.activeTextStyle;

  let ff = 'sans-serif';
  if (style.fontFamily === 'serif') ff = 'serif';
  if (style.fontFamily === 'mono') ff = 'monospace';

  input.style.fontFamily = ff;
  input.style.fontSize = `${style.fontSize * s}px`;
  input.style.fontWeight = style.bold ? '700' : '400';
  input.style.fontStyle = style.italic ? 'italic' : 'normal';
  input.style.color = style.color;
  input.style.textAlign = style.align || 'left';
}

function positionFloatingToolbar(x, y) {
  const toolbar = $('floating-text-toolbar');
  toolbar.style.left = `${Math.max(x, 10)}px`;
  toolbar.style.top = `${Math.max(y, 10)}px`;
  toolbar.classList.remove('hidden');
}

function syncToolbarControls() {
  const style = appState.activeTextStyle;
  $('fmt-font-family').value = style.fontFamily;
  $('fmt-size-input').value = style.fontSize;
  $('fmt-bold').classList.toggle('active', style.bold);
  $('fmt-italic').classList.toggle('active', style.italic);
  $('fmt-color').value = style.color;
  $('fmt-color-indicator').style.background = style.color;

  // Alignment buttons sync
  document.querySelectorAll('.fmt-align').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.align === (style.align || 'left'));
  });
}

function adjustFontSize(delta) {
  appState.activeTextStyle.fontSize = Math.max(4, Math.round((appState.activeTextStyle.fontSize + delta) * 10) / 10);
  appState.activeTextStyle.sizeModified = true;
  $('fmt-size-input').value = appState.activeTextStyle.fontSize;
  updateInlineInputVisuals();
}

async function commitInlineEdit() {
  const input = $('inline-input');
  const newText = input.textContent.trim();
  const td = appState.textDrag || {};

  if (appState.editingSpan) {
    const span = appState.editingSpan;
    closeInlineEditor();

    // If dragged/repositioned, use exact targetPdfX / targetPdfY; otherwise preserve original baseline origin
    const targetX = td.moved ? td.targetPdfX : null;
    const targetY = td.moved ? td.targetPdfY : null;

    try {
      const payload = await apiFetch('/api/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: appState.sessionId,
          page_num: appState.pageNum,
          span_id: span.id,
          new_text: newText,
          font_size: appState.activeTextStyle.sizeModified ? appState.activeTextStyle.fontSize : span.size,
          font_family: appState.activeTextStyle.fontFamily,
          color: appState.activeTextStyle.color,
          bold: appState.activeTextStyle.bold,
          italic: appState.activeTextStyle.italic,
          x: targetX,
          y: targetY,
          align: appState.activeTextStyle.align || 'left',
        }),
      });
      applyPagePayload(payload);
      updateHistoryButtons(true, false);
      showToast(targetX ? 'Text moved & placed!' : 'Text updated successfully!', 'success');
      loadThumbnails();
    } catch (err) {
      console.error(err);
    }

  } else if (appState.isNewText && appState.newTextPt) {
    if (!newText) {
      closeInlineEditor();
      return;
    }
    const pt = appState.newTextPt;
    const targetX = td.moved ? td.targetPdfX : pt.x;
    const targetY = td.moved ? td.targetPdfY : pt.y;
    closeInlineEditor();

    try {
      const payload = await apiFetch('/api/add_text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: appState.sessionId,
          page_num: appState.pageNum,
          x: targetX,
          y: targetY,
          text: newText,
          fontsize: appState.activeTextStyle.fontSize,
          font_family: appState.activeTextStyle.fontFamily,
          color: appState.activeTextStyle.color,
          bold: appState.activeTextStyle.bold,
          italic: appState.activeTextStyle.italic,
          align: appState.activeTextStyle.align || 'left',
        }),
      });
      applyPagePayload(payload);
      updateHistoryButtons(true, false);
      showToast('Text placed on document!', 'success');
      loadThumbnails();
    } catch (err) {
      console.error(err);
    }
  }
}

async function deleteCurrentText() {
  if (!appState.editingSpan) {
    closeInlineEditor();
    return;
  }
  const span = appState.editingSpan;
  closeInlineEditor();

  try {
    const payload = await apiFetch('/api/delete_text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: appState.pageNum,
        span_id: span.id,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(true, false);
    showToast('Text deleted.', 'info');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
}

function closeInlineEditor() {
  $('inline-editor').classList.add('hidden');
  $('floating-text-toolbar').classList.add('hidden');
  appState.editingSpan = null;
  appState.isNewText = false;
  appState.newTextPt = null;
}

// ==========================================================================
// Drawing Canvas (Whiteout, Shapes, Annotations)
// ==========================================================================

function initDrawingCanvas() {
  const canvas = $('drawing-canvas');
  const ctx = canvas.getContext('2d');

  canvas.addEventListener('mousedown', (e) => {
    if (!['whiteout', 'annotate', 'shapes'].includes(appState.activeTool)) return;
    const rect = canvas.getBoundingClientRect();
    appState.drawState.isDrawing = true;
    appState.drawState.startX = e.clientX - rect.left;
    appState.drawState.startY = e.clientY - rect.top;
    appState.drawState.currentX = appState.drawState.startX;
    appState.drawState.currentY = appState.drawState.startY;
    appState.drawState.points = [[appState.drawState.startX, appState.drawState.startY]];
  });

  canvas.addEventListener('mousemove', (e) => {
    if (!appState.drawState.isDrawing) return;
    const rect = canvas.getBoundingClientRect();
    appState.drawState.currentX = e.clientX - rect.left;
    appState.drawState.currentY = e.clientY - rect.top;
    appState.drawState.points.push([appState.drawState.currentX, appState.drawState.currentY]);

    // Render live preview on canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    renderDrawingPreview(ctx);
  });

  canvas.addEventListener('mouseup', async () => {
    if (!appState.drawState.isDrawing) return;
    appState.drawState.isDrawing = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    await commitDrawingAction();
  });
}

function renderDrawingPreview(ctx) {
  const { startX, startY, currentX, currentY, points } = appState.drawState;
  const tool = appState.activeTool;

  if (tool === 'whiteout') {
    const x = Math.min(startX, currentX);
    const y = Math.min(startY, currentY);
    const w = Math.abs(currentX - startX);
    const h = Math.abs(currentY - startY);
    ctx.fillStyle = (appState.toolSettings.whiteout.mode === 'white') ? '#ffffff' : '#000000';
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = '#2563eb';
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, w, h);

  } else if (tool === 'annotate') {
    const ann = appState.toolSettings.annotate;
    if (ann.type === 'highlight') {
      const x = Math.min(startX, currentX);
      const y = Math.min(startY, currentY);
      const w = Math.abs(currentX - startX);
      const h = Math.abs(currentY - startY);
      ctx.fillStyle = ann.color;
      ctx.globalAlpha = ann.opacity;
      ctx.fillRect(x, y, w, h);
      ctx.globalAlpha = 1.0;
    } else if (ann.type === 'pen') {
      if (points.length < 2) return;
      ctx.strokeStyle = ann.color;
      ctx.lineWidth = ann.penWidth;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i][0], points[i][1]);
      }
      ctx.stroke();
    }

  } else if (tool === 'shapes') {
    const shp = appState.toolSettings.shapes;
    ctx.strokeStyle = shp.stroke;
    ctx.lineWidth = shp.width;

    if (shp.type === 'rect') {
      const x = Math.min(startX, currentX);
      const y = Math.min(startY, currentY);
      const w = Math.abs(currentX - startX);
      const h = Math.abs(currentY - startY);
      ctx.strokeRect(x, y, w, h);

    } else if (shp.type === 'circle') {
      const x = Math.min(startX, currentX);
      const y = Math.min(startY, currentY);
      const w = Math.abs(currentX - startX);
      const h = Math.abs(currentY - startY);
      ctx.beginPath();
      ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
      ctx.stroke();

    } else if (shp.type === 'line' || shp.type === 'arrow') {
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(currentX, currentY);
      ctx.stroke();

      if (shp.type === 'arrow') {
        const angle = Math.atan2(currentY - startY, currentX - startX);
        const arrowSize = 12;
        ctx.fillStyle = shp.stroke;
        ctx.beginPath();
        ctx.moveTo(currentX, currentY);
        ctx.lineTo(currentX - arrowSize * Math.cos(angle - Math.PI / 6), currentY - arrowSize * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(currentX - arrowSize * Math.cos(angle + Math.PI / 6), currentY - arrowSize * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fill();
      }
    }
  }
}

async function commitDrawingAction() {
  const { startX, startY, currentX, currentY, points } = appState.drawState;
  const tool = appState.activeTool;

  const p1 = screenToPdf(startX, startY);
  const p2 = screenToPdf(currentX, currentY);

  const x0 = Math.min(p1.x, p2.x);
  const y0 = Math.min(p1.y, p2.y);
  const x1 = Math.max(p1.x, p2.x);
  const y1 = Math.max(p1.y, p2.y);

  if (tool === 'whiteout') {
    if (Math.abs(currentX - startX) < 4 || Math.abs(currentY - startY) < 4) return;
    try {
      const payload = await apiFetch('/api/whiteout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: appState.sessionId,
          page_num: appState.pageNum,
          rect: [x0, y0, x1, y1],
          fill_color: appState.toolSettings.whiteout.fill,
          redact: appState.toolSettings.whiteout.redact,
        }),
      });
      applyPagePayload(payload);
      updateHistoryButtons(true, false);
      showToast('Whiteout applied cleanly.', 'success');
      loadThumbnails();
    } catch (err) {
      console.error(err);
    }

  } else if (tool === 'annotate') {
    const ann = appState.toolSettings.annotate;
    if (ann.type === 'highlight') {
      if (Math.abs(currentX - startX) < 4 || Math.abs(currentY - startY) < 4) return;
      try {
        const payload = await apiFetch('/api/highlight', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: appState.sessionId,
            page_num: appState.pageNum,
            rect: [x0, y0, x1, y1],
            color: ann.color,
            opacity: ann.opacity,
          }),
        });
        applyPagePayload(payload);
        updateHistoryButtons(true, false);
        showToast('Highlight added.', 'success');
        loadThumbnails();
      } catch (err) {
        console.error(err);
      }
    } else if (ann.type === 'pen') {
      if (points.length < 3) return;
      const pdfPoints = points.map(pt => {
        const p = screenToPdf(pt[0], pt[1]);
        return [p.x, p.y];
      });
      try {
        const payload = await apiFetch('/api/freehand', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: appState.sessionId,
            page_num: appState.pageNum,
            points: pdfPoints,
            stroke_color: ann.color,
            stroke_width: ann.penWidth,
            opacity: 1.0,
          }),
        });
        applyPagePayload(payload);
        updateHistoryButtons(true, false);
        showToast('Drawing added.', 'success');
        loadThumbnails();
      } catch (err) {
        console.error(err);
      }
    }

  } else if (tool === 'shapes') {
    const shp = appState.toolSettings.shapes;
    let coords;
    if (['line', 'arrow'].includes(shp.type)) {
      coords = [p1.x, p1.y, p2.x, p2.y];
    } else {
      coords = [x0, y0, x1, y1];
    }
    try {
      const payload = await apiFetch('/api/shape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: appState.sessionId,
          page_num: appState.pageNum,
          shape_type: shp.type,
          coords: coords,
          stroke_color: shp.stroke,
          fill_color: shp.fill,
          stroke_width: shp.width,
        }),
      });
      applyPagePayload(payload);
      updateHistoryButtons(true, false);
      showToast('Shape created.', 'success');
      loadThumbnails();
    } catch (err) {
      console.error(err);
    }
  }
}

// ==========================================================================
// Transform Box (Dragging & Resizing Images & Signatures)
// ==========================================================================

function openTransformBox(dataUrl, defaultWidthPt = 160, defaultHeightPt = 60) {
  appState.transform.active = true;
  appState.transform.imgData = dataUrl;
  appState.transform.x = 100;
  appState.transform.y = 120;
  appState.transform.width = defaultWidthPt;
  appState.transform.height = defaultHeightPt;

  const box = $('transform-box');
  const img = $('transform-preview-img');
  img.src = dataUrl;

  updateTransformBoxStyles();
  box.classList.remove('hidden');
}

function updateTransformBoxStyles() {
  const box = $('transform-box');
  const s = scaleFactor();
  box.style.left = `${appState.transform.x * s}px`;
  box.style.top = `${appState.transform.y * s}px`;
  box.style.width = `${appState.transform.width * s}px`;
  box.style.height = `${appState.transform.height * s}px`;
}

function cancelTransformBox() {
  $('transform-box').classList.add('hidden');
  appState.transform.active = false;
  appState.transform.imgData = null;
}

function initTransformBoxEvents() {
  const box = $('transform-box');

  box.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('resize-handle')) {
      appState.transform.isResizing = true;
      appState.transform.activeHandle = e.target.dataset.handle;
    } else {
      appState.transform.isDragging = true;
    }
    appState.transform.dragStartX = e.clientX;
    appState.transform.dragStartY = e.clientY;
    appState.transform.initialBox = { ...appState.transform };
    e.stopPropagation();
  });

  window.addEventListener('mousemove', (e) => {
    if (!appState.transform.active) return;
    const s = scaleFactor();

    if (appState.transform.isDragging) {
      const dx = (e.clientX - appState.transform.dragStartX) / s;
      const dy = (e.clientY - appState.transform.dragStartY) / s;
      appState.transform.x = Math.max(0, appState.transform.initialBox.x + dx);
      appState.transform.y = Math.max(0, appState.transform.initialBox.y + dy);
      updateTransformBoxStyles();

    } else if (appState.transform.isResizing) {
      const dx = (e.clientX - appState.transform.dragStartX) / s;
      const dy = (e.clientY - appState.transform.dragStartY) / s;
      const init = appState.transform.initialBox;

      if (appState.transform.activeHandle === 'se') {
        appState.transform.width = Math.max(20, init.width + dx);
        appState.transform.height = Math.max(15, init.height + dy);
      } else if (appState.transform.activeHandle === 'sw') {
        appState.transform.x = init.x + dx;
        appState.transform.width = Math.max(20, init.width - dx);
        appState.transform.height = Math.max(15, init.height + dy);
      } else if (appState.transform.activeHandle === 'ne') {
        appState.transform.y = init.y + dy;
        appState.transform.width = Math.max(20, init.width + dx);
        appState.transform.height = Math.max(15, init.height - dy);
      } else if (appState.transform.activeHandle === 'nw') {
        appState.transform.x = init.x + dx;
        appState.transform.y = init.y + dy;
        appState.transform.width = Math.max(20, init.width - dx);
        appState.transform.height = Math.max(15, init.height - dy);
      }
      updateTransformBoxStyles();
    }
  });

  window.addEventListener('mouseup', () => {
    appState.transform.isDragging = false;
    appState.transform.isResizing = false;
    appState.transform.activeHandle = null;
  });

  $('confirm-transform-btn').addEventListener('click', commitTransformPlacement);
  $('cancel-transform-btn').addEventListener('click', cancelTransformBox);
}

async function commitTransformPlacement() {
  if (!appState.transform.active || !appState.transform.imgData) return;

  const { x, y, width, height, imgData } = appState.transform;
  cancelTransformBox();

  try {
    const payload = await apiFetch('/api/add_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: appState.pageNum,
        image_base64: imgData,
        rect: [x, y, x + width, y + height],
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(true, false);
    showToast('Placed successfully!', 'success');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================================================
// Signature Modal & Creation Pad
// ==========================================================================

function initSignaturePad() {
  const canvas = $('sig-pad-canvas');
  const ctx = canvas.getContext('2d');
  appState.sigPad.canvas = canvas;
  appState.sigPad.ctx = ctx;

  canvas.addEventListener('mousedown', (e) => {
    const rect = canvas.getBoundingClientRect();
    appState.sigPad.isDrawing = true;
    appState.sigPad.lastX = e.clientX - rect.left;
    appState.sigPad.lastY = e.clientY - rect.top;
  });

  canvas.addEventListener('mousemove', (e) => {
    if (!appState.sigPad.isDrawing) return;
    const rect = canvas.getBoundingClientRect();
    const currentX = e.clientX - rect.left;
    const currentY = e.clientY - rect.top;

    ctx.strokeStyle = appState.sigPad.inkColor;
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    ctx.beginPath();
    ctx.moveTo(appState.sigPad.lastX, appState.sigPad.lastY);
    ctx.lineTo(currentX, currentY);
    ctx.stroke();

    appState.sigPad.lastX = currentX;
    appState.sigPad.lastY = currentY;
    appState.sigPad.hasSignature = true;
  });

  window.addEventListener('mouseup', () => {
    appState.sigPad.isDrawing = false;
  });

  $('clear-sig-pad').addEventListener('click', () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    appState.sigPad.hasSignature = false;
  });

  document.querySelectorAll('.color-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      document.querySelectorAll('.color-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      appState.sigPad.inkColor = chip.dataset.color;
    });
  });
}

function initSignatureModal() {
  // Modal tabs
  document.querySelectorAll('.modal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.dataset.sigTab;
      $('sig-tab-draw').classList.toggle('hidden', target !== 'draw');
      $('sig-tab-type').classList.toggle('hidden', target !== 'type');
      $('sig-tab-upload').classList.toggle('hidden', target !== 'upload');
    });
  });

  // Type signature name input
  $('sig-name-input').addEventListener('input', (e) => {
    const name = e.target.value || 'Signature';
    document.querySelectorAll('.sig-style-preview').forEach(p => p.textContent = name);
  });

  // Type signature card selection
  document.querySelectorAll('.sig-style-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.sig-style-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      appState.sigTypeFont = card.dataset.font;
    });
  });

  // Signature file upload
  $('sig-file-input').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        appState.uploadedSigData = ev.target.result;
        $('sig-upload-img').src = ev.target.result;
        $('sig-upload-preview').classList.remove('hidden');
      };
      reader.readAsDataURL(file);
    }
  });

  $('close-sig-modal').addEventListener('click', closeSignatureModal);
  $('cancel-sig-btn').addEventListener('click', closeSignatureModal);
  $('save-sig-btn').addEventListener('click', handleSaveSignature);
}

function openSignatureModal() {
  $('signature-modal').classList.remove('hidden');
}

function closeSignatureModal() {
  $('signature-modal').classList.add('hidden');
}

function handleSaveSignature() {
  const activeTab = document.querySelector('.modal-tab.active').dataset.sigTab;
  let finalDataUrl = null;

  if (activeTab === 'draw') {
    if (!appState.sigPad.hasSignature) {
      showToast('Please draw a signature first.', 'error');
      return;
    }
    finalDataUrl = appState.sigPad.canvas.toDataURL('image/png');

  } else if (activeTab === 'type') {
    const name = $('sig-name-input').value.trim() || 'John Doe';
    // Render text to temporary canvas with cursive font
    const offCanvas = document.createElement('canvas');
    offCanvas.width = 400;
    offCanvas.height = 120;
    const offCtx = offCanvas.getContext('2d');
    offCtx.font = `56px '${appState.sigTypeFont}', cursive`;
    offCtx.fillStyle = '#0d47a1';
    offCtx.textBaseline = 'middle';
    offCtx.fillText(name, 20, 60);
    finalDataUrl = offCanvas.toDataURL('image/png');

  } else if (activeTab === 'upload') {
    if (!appState.uploadedSigData) {
      showToast('Please select a signature image.', 'error');
      return;
    }
    finalDataUrl = appState.uploadedSigData;
  }

  closeSignatureModal();
  openTransformBox(finalDataUrl, 160, 55);
  showToast('Signature ready! Drag to desired position and click ✓ Place.', 'info');
}

// ==========================================================================
// Image Tool Handling
// ==========================================================================

function handleImageToolFile(e) {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (ev) => {
    openTransformBox(ev.target.result, 180, 120);
    showToast('Image ready! Position, resize, and click ✓ Place.', 'info');
  };
  reader.readAsDataURL(file);
  e.target.value = ''; // Reset input
}

// ==========================================================================
// Page Organization & Thumbnails Drawer
// ==========================================================================

function toggleThumbnailsDrawer() {
  const drawer = $('thumbnails-drawer');
  appState.thumbnailsOpen = !appState.thumbnailsOpen;
  drawer.classList.toggle('collapsed', !appState.thumbnailsOpen);
  if (appState.thumbnailsOpen) {
    loadThumbnails();
  }
}

async function loadThumbnails() {
  if (!appState.sessionId || !appState.thumbnailsOpen) return;

  try {
    const data = await apiFetch(`/api/thumbnails/${appState.sessionId}`);
    renderThumbnailsList(data.thumbnails);
  } catch (err) {
    console.error('Thumbnail error:', err);
  }
}

function renderThumbnailsList(thumbs) {
  const list = $('thumbnails-list');
  list.innerHTML = '';
  $('thumb-count-val').textContent = thumbs.length;

  thumbs.forEach((t) => {
    const card = document.createElement('div');
    card.className = `thumb-card ${t.page_num === appState.pageNum ? 'active' : ''}`;
    card.dataset.pageNum = t.page_num;

    card.innerHTML = `
      <img src="data:image/png;base64,${t.image_base64}" class="thumb-img" alt="Page ${t.page_num + 1}" />
      <div class="thumb-footer">
        <span class="thumb-num">Page ${t.page_num + 1}</span>
        <div class="thumb-actions">
          <button class="thumb-btn" title="Rotate 90° clockwise" onclick="rotatePage(${t.page_num}, 90); event.stopPropagation();">↻</button>
          <button class="thumb-btn" title="Duplicate page" onclick="duplicatePage(${t.page_num}); event.stopPropagation();">📋</button>
          <button class="thumb-btn danger" title="Delete page" onclick="deletePage(${t.page_num}); event.stopPropagation();">🗑️</button>
        </div>
      </div>
    `;

    card.addEventListener('click', () => goToPage(t.page_num));
    list.appendChild(card);
  });
}

function highlightActiveThumbnail() {
  document.querySelectorAll('.thumb-card').forEach(c => {
    c.classList.toggle('active', parseInt(c.dataset.pageNum, 10) === appState.pageNum);
  });
}

window.rotatePage = async function(pageNum, angle = 90) {
  try {
    const payload = await apiFetch('/api/page/rotate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: pageNum,
        angle: angle,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(true, false);
    showToast(`Page ${pageNum + 1} rotated.`, 'info');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
};

window.duplicatePage = async function(pageNum) {
  try {
    const payload = await apiFetch('/api/page/duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: pageNum,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(true, false);
    showToast(`Page ${pageNum + 1} duplicated.`, 'success');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
};

window.deletePage = async function(pageNum) {
  if (appState.pageCount <= 1) {
    showToast('Cannot delete the only page in the document.', 'error');
    return;
  }
  if (!confirm(`Delete Page ${pageNum + 1}?`)) return;

  try {
    const payload = await apiFetch('/api/page/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: pageNum,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(true, false);
    showToast(`Page ${pageNum + 1} deleted.`, 'info');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
};

window.insertBlankPage = async function() {
  try {
    const payload = await apiFetch('/api/page/insert_blank', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        at_page_num: appState.pageNum + 1,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(true, false);
    showToast('Blank page inserted.', 'success');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
};

// ==========================================================================
// Find & Replace Modal
// ==========================================================================

function initFindReplaceModal() {
  $('close-find-modal').addEventListener('click', closeFindReplaceModal);
  $('cancel-find-btn').addEventListener('click', closeFindReplaceModal);
  $('execute-replace-btn').addEventListener('click', executeFindReplace);
}

function openFindReplaceModal() {
  $('find-replace-modal').classList.remove('hidden');
  setTimeout(() => $('find-search-input').focus(), 10);
}

function closeFindReplaceModal() {
  $('find-replace-modal').classList.add('hidden');
}

async function executeFindReplace() {
  const search = $('find-search-input').value;
  const replace = $('find-replace-input').value;
  const matchCase = $('find-case-check').checked;
  const allPages = $('find-allpages-check').checked;

  if (!search.trim()) {
    showToast('Please enter text to find.', 'error');
    return;
  }

  closeFindReplaceModal();

  try {
    const payload = await apiFetch('/api/find_replace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        search_text: search,
        replace_text: replace,
        page_num: allPages ? null : appState.pageNum,
        match_case: matchCase,
      }),
    });
    applyPagePayload(payload);
    const count = payload.replaced_count || 0;
    if (count > 0) {
      updateHistoryButtons(true, false);
      showToast(`Replaced ${count} occurrence(s) successfully!`, 'success');
      loadThumbnails();
    } else {
      showToast('No matching text found.', 'info');
    }
  } catch (err) {
    console.error(err);
  }
}

// ==========================================================================
// Undo / Redo / Export
// ==========================================================================

function updateHistoryButtons(canUndo, canRedo) {
  $('undo-btn').disabled = !canUndo;
  $('redo-btn').disabled = !canRedo;
}

async function performUndo() {
  if (!appState.sessionId) return;
  closeInlineEditor();
  cancelTransformBox();

  try {
    const payload = await apiFetch('/api/undo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: appState.pageNum,
        zoom: appState.zoom,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(payload.can_undo, payload.can_redo);
    showToast('Undid change.', 'info');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
}

async function performRedo() {
  if (!appState.sessionId) return;
  closeInlineEditor();
  cancelTransformBox();

  try {
    const payload = await apiFetch('/api/redo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: appState.sessionId,
        page_num: appState.pageNum,
        zoom: appState.zoom,
      }),
    });
    applyPagePayload(payload);
    updateHistoryButtons(payload.can_undo, payload.can_redo);
    showToast('Redid change.', 'info');
    loadThumbnails();
  } catch (err) {
    console.error(err);
  }
}

function exportPdf() {
  if (!appState.sessionId) return;
  window.location.href = `/api/export/${appState.sessionId}`;
  showToast('Exporting clean PDF! Check your downloads.', 'success');
}
