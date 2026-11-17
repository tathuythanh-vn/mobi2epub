/**
 * Frontend application logic for MOBI to EPUB Converter (Web Edition).
 * Communicates with docs/worker.js (Pyodide + mobi2epub + KindleUnpack).
 */

const SUPPORTED_EXTENSIONS = [".mobi", ".prc", ".azw3", ".azw"];

const state = {
  worker: null,
  engineReady: false,
  engineError: null,
  queuedFiles: [], // Array of { file: File, name: string, relPath: string, size: number }
  convertedItems: new Map(), // Map<outRelPath, { outFileName, outRelPath, title, size, blobUrl, buffer }>
  isRunning: false,
  cancelRequested: false,
  startTime: 0,
  elapsedTimerId: null,
  nextJobId: 1,
  pendingResolvers: new Map(),
  autoConvertOnReady: false,
};

// DOM Elements
const els = {
  enginePill: document.getElementById("enginePill"),
  engineStatusText: document.getElementById("engineStatusText"),
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("fileInput"),
  folderInput: document.getElementById("folderInput"),
  btnAddFiles: document.getElementById("btnAddFiles"),
  btnSelectFolder: document.getElementById("btnSelectFolder"),
  btnTrySample: document.getElementById("btnTrySample"),
  btnClearQueue: document.getElementById("btnClearQueue"),
  inputSummaryText: document.getElementById("inputSummaryText"),
  queuedList: document.getElementById("queuedList"),
  chkRecursive: document.getElementById("chkRecursive"),
  chkForce: document.getElementById("chkForce"),
  btnConvert: document.getElementById("btnConvert"),
  btnCancel: document.getElementById("btnCancel"),
  progressTrack: document.getElementById("progressTrack"),
  progressFill: document.getElementById("progressFill"),
  statusText: document.getElementById("statusText"),
  elapsedText: document.getElementById("elapsedText"),
  logBox: document.getElementById("logBox"),
  btnClearLog: document.getElementById("btnClearLog"),
  summaryText: document.getElementById("summaryText"),
  downloadsList: document.getElementById("downloadsList"),
  btnDownloadAllZip: document.getElementById("btnDownloadAllZip"),
  convertedCountBadge: document.getElementById("convertedCountBadge"),
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hasSupportedExtension(filename) {
  const lower = (filename || "").toLowerCase();
  return SUPPORTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function naturalSortKey(str) {
  return String(str)
    .toLowerCase()
    .split(/(\d+)/)
    .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
}

function compareNatural(a, b) {
  const ka = naturalSortKey(a);
  const kb = naturalSortKey(b);
  const len = Math.min(ka.length, kb.length);
  for (let i = 0; i < len; i++) {
    if (ka[i] !== kb[i]) {
      return ka[i] < kb[i] ? -1 : 1;
    }
  }
  return ka.length - kb.length;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(2)} MB`;
}

function formatElapsed(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `Elapsed: ${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function appendLog(text, type = "info") {
  const p = document.createElement("div");
  p.className = `log-line log-${type}`;
  p.textContent = text;
  els.logBox.appendChild(p);
  els.logBox.scrollTop = els.logBox.scrollHeight;
}

function clearLog() {
  els.logBox.innerHTML = "";
}

// ---------------------------------------------------------------------------
// Web Worker Setup
// ---------------------------------------------------------------------------

function initWorker() {
  const worker = new Worker("./worker.js");
  state.worker = worker;

  worker.onmessage = (event) => {
    const msg = event.data;
    if (!msg || !msg.type) return;

    if (msg.type === "init_status") {
      els.enginePill.className = "engine-pill loading";
      els.engineStatusText.textContent = msg.message || "Loading Python engine...";
    } else if (msg.type === "ready") {
      state.engineReady = true;
      state.engineError = null;
      els.enginePill.className = "engine-pill ready";
      els.engineStatusText.textContent = `Engine Ready · ${msg.engine || "KindleUnpack WASM"}`;
      appendLog("[INFO] Pyodide WebAssembly engine initialized (mobi2epub + KindleUnpack ready).", "info");
      updateControlsState();

      if (state.autoConvertOnReady && state.queuedFiles.length > 0 && !state.isRunning) {
        state.autoConvertOnReady = false;
        startBatchConversion();
      }
    } else if (msg.type === "init_error") {
      state.engineReady = false;
      state.engineError = msg.message || "Failed to initialize Pyodide";
      els.enginePill.className = "engine-pill error";
      els.engineStatusText.textContent = "Engine Error";
      appendLog(`[ERROR] Failed to load WebAssembly Python engine: ${state.engineError}`, "fail");
      updateControlsState();
    } else if (msg.type === "file_result" || msg.type === "zip_result") {
      const resolver = state.pendingResolvers.get(msg.id);
      if (resolver) {
        state.pendingResolvers.delete(msg.id);
        resolver(msg);
      }
    }
  };

  worker.onerror = (err) => {
    const message = err && err.message ? err.message : "Worker runtime error";
    els.enginePill.className = "engine-pill error";
    els.engineStatusText.textContent = "Worker Error";
    appendLog(`[ERROR] Worker error: ${message}`, "fail");
  };

  worker.postMessage({ type: "init" });
}

function callWorker(payload, transfer = []) {
  return new Promise((resolve) => {
    const id = state.nextJobId++;
    state.pendingResolvers.set(id, resolve);
    state.worker.postMessage({ ...payload, id }, transfer);
  });
}

// ---------------------------------------------------------------------------
// File Queue Management
// ---------------------------------------------------------------------------

function addFilesToQueue(fileEntries, replace = false) {
  const recursive = els.chkRecursive.checked;
  const filtered = [];

  for (const item of fileEntries) {
    const file = item.file || item;
    const relPath = (item.relPath || file.webkitRelativePath || file.name || "").replace(/\\/g, "/");
    if (!hasSupportedExtension(file.name)) continue;

    // If folder selection and recursive is unchecked, skip files nested deeper than top-level folder
    if (!recursive && relPath.split("/").length > 2) {
      continue;
    }

    filtered.push({
      file,
      name: file.name,
      relPath: relPath || file.name,
      size: file.size || 0,
    });
  }

  if (filtered.length === 0) {
    appendLog("[INFO] No supported MOBI files (.mobi, .prc, .azw3, .azw) found in selection.", "skip");
    return 0;
  }

  const nextQueue = replace ? [] : [...state.queuedFiles];
  const existingKeys = new Set(nextQueue.map((q) => `${q.relPath}::${q.size}`));

  for (const entry of filtered) {
    const key = `${entry.relPath}::${entry.size}`;
    if (!existingKeys.has(key)) {
      existingKeys.add(key);
      nextQueue.push(entry);
    }
  }

  nextQueue.sort((a, b) => compareNatural(a.relPath, b.relPath));
  state.queuedFiles = nextQueue;
  renderQueue();
  updateControlsState();
  return filtered.length;
}

function removeQueuedIndex(idx) {
  if (state.isRunning) return;
  state.queuedFiles.splice(idx, 1);
  renderQueue();
  updateControlsState();
}

function clearQueue() {
  if (state.isRunning) return;
  state.queuedFiles = [];
  renderQueue();
  updateControlsState();
}

function renderQueue() {
  const count = state.queuedFiles.length;
  if (count === 0) {
    els.inputSummaryText.textContent = "No files selected — drop .mobi files above or click Add files...";
    els.queuedList.classList.add("hidden");
    els.queuedList.innerHTML = "";
    els.btnClearQueue.classList.add("hidden");
    return;
  }

  if (count === 1) {
    const f = state.queuedFiles[0];
    els.inputSummaryText.textContent = `${f.relPath} (${formatBytes(f.size)})`;
  } else {
    const totalBytes = state.queuedFiles.reduce((acc, item) => acc + item.size, 0);
    els.inputSummaryText.textContent = `${count} files selected (${formatBytes(totalBytes)}): ${state.queuedFiles[0].name}, ...`;
  }

  els.btnClearQueue.classList.remove("hidden");
  els.queuedList.classList.remove("hidden");
  els.queuedList.innerHTML = "";

  state.queuedFiles.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "queued-item";

    const nameSpan = document.createElement("span");
    nameSpan.className = "queued-item-name";
    nameSpan.textContent = item.relPath;

    const metaSpan = document.createElement("span");
    metaSpan.className = "queued-item-meta";
    metaSpan.textContent = formatBytes(item.size);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-remove-item";
    removeBtn.title = "Remove file";
    removeBtn.textContent = "×";
    removeBtn.disabled = state.isRunning;
    removeBtn.addEventListener("click", () => removeQueuedIndex(index));

    metaSpan.appendChild(removeBtn);
    row.appendChild(nameSpan);
    row.appendChild(metaSpan);
    els.queuedList.appendChild(row);
  });
}

function updateControlsState() {
  const hasFiles = state.queuedFiles.length > 0;
  els.btnConvert.disabled = state.isRunning || !hasFiles;
  els.btnCancel.disabled = !state.isRunning;
  els.btnAddFiles.disabled = state.isRunning;
  els.btnSelectFolder.disabled = state.isRunning;
  els.btnTrySample.disabled = state.isRunning;
  els.btnClearQueue.disabled = state.isRunning || !hasFiles;
  els.chkRecursive.disabled = state.isRunning;
  els.chkForce.disabled = state.isRunning;
  els.btnDownloadAllZip.disabled = state.isRunning || state.convertedItems.size < 1;
}

// ---------------------------------------------------------------------------
// Drag & Drop Directory Traversal
// ---------------------------------------------------------------------------

async function readDirectoryEntryRecursive(dirEntry, prefix = "") {
  const results = [];
  const reader = dirEntry.createReader();

  const readBatch = () =>
    new Promise((resolve) => {
      reader.readEntries(
        (entries) => resolve(entries || []),
        () => resolve([])
      );
    });

  while (true) {
    const entries = await readBatch();
    if (!entries.length) break;
    for (const entry of entries) {
      const nextRel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isFile) {
        const file = await new Promise((resolve) => entry.file(resolve, () => resolve(null)));
        if (file) {
          results.push({ file, relPath: nextRel });
        }
      } else if (entry.isDirectory && els.chkRecursive.checked) {
        const subFiles = await readDirectoryEntryRecursive(entry, nextRel);
        results.push(...subFiles);
      }
    }
  }
  return results;
}

async function extractDroppedItems(dataTransfer) {
  const items = dataTransfer.items;
  if (items && items.length > 0 && typeof items[0].webkitGetAsEntry === "function") {
    const collected = [];
    const entries = [];
    for (let i = 0; i < items.length; i++) {
      const entry = items[i].webkitGetAsEntry();
      if (entry) entries.push(entry);
    }

    for (const entry of entries) {
      if (entry.isFile) {
        const file = await new Promise((resolve) => entry.file(resolve, () => resolve(null)));
        if (file) collected.push({ file, relPath: file.name });
      } else if (entry.isDirectory) {
        const sub = await readDirectoryEntryRecursive(entry, entry.name);
        collected.push(...sub);
      }
    }
    return collected;
  }

  return Array.from(dataTransfer.files || []).map((file) => ({
    file,
    relPath: file.webkitRelativePath || file.name,
  }));
}

// ---------------------------------------------------------------------------
// Conversion Execution
// ---------------------------------------------------------------------------

function startElapsedTimer() {
  state.startTime = performance.now();
  els.elapsedText.textContent = "Elapsed: 00:00";
  if (state.elapsedTimerId) clearInterval(state.elapsedTimerId);
  state.elapsedTimerId = setInterval(() => {
    const sec = (performance.now() - state.startTime) / 1000;
    els.elapsedText.textContent = formatElapsed(sec);
  }, 250);
}

function stopElapsedTimer() {
  if (state.elapsedTimerId) {
    clearInterval(state.elapsedTimerId);
    state.elapsedTimerId = null;
  }
}

function setProgress(index, total, indeterminate = false) {
  if (indeterminate) {
    els.progressTrack.classList.add("indeterminate");
    els.progressFill.style.width = "35%";
  } else {
    els.progressTrack.classList.remove("indeterminate");
    const pct = total > 0 ? Math.min(100, Math.round((index / total) * 100)) : 0;
    els.progressFill.style.width = `${pct}%`;
  }
}

async function startBatchConversion() {
  if (state.isRunning || state.queuedFiles.length === 0) return;

  if (!state.engineReady) {
    state.autoConvertOnReady = true;
    els.statusText.textContent = "Waiting for Pyodide engine to finish loading...";
    appendLog("[INFO] Conversion queued — will start automatically as soon as Pyodide is ready.", "info");
    return;
  }

  state.isRunning = true;
  state.cancelRequested = false;
  els.btnCancel.textContent = "Cancel";
  updateControlsState();
  renderQueue();

  const tasks = [...state.queuedFiles];
  const total = tasks.length;
  const forceOverwrite = els.chkForce.checked;

  let convertedCount = 0;
  let skippedCount = 0;
  let failedCount = 0;

  startElapsedTimer();
  els.summaryText.textContent = "";

  if (total === 1) {
    setProgress(0, 1, true);
  } else {
    setProgress(0, total, false);
  }

  appendLog(`Starting conversion of ${total} file(s)...`, "info");

  for (let i = 0; i < total; i++) {
    if (state.cancelRequested) {
      break;
    }

    const idx = i + 1;
    const item = tasks[i];
    const expectedOutRel = item.relPath.replace(/\.[^/.]+$/, "") + ".epub";

    els.statusText.textContent = `${idx} / ${total} · ${item.name}`;

    // Overwrite check matching desktop runner
    if (!forceOverwrite && state.convertedItems.has(expectedOutRel)) {
      skippedCount++;
      if (total > 1) setProgress(idx, total, false);
      appendLog(`[SKIPPED] ${item.relPath} (Destination already exists)`, "skip");
      continue;
    }

    try {
      const arrayBuffer = await item.file.arrayBuffer();
      const res = await callWorker(
        {
          type: "convert_file",
          fileName: item.name,
          relPath: item.relPath,
          data: arrayBuffer,
        },
        [arrayBuffer]
      );

      if (total > 1) {
        setProgress(idx, total, false);
      }

      if (res.success && res.epubData) {
        convertedCount++;
        const epubBytes = res.epubData;
        const blob = new Blob([epubBytes], { type: "application/epub+zip" });
        const blobUrl = URL.createObjectURL(blob);

        // Revoke previous blob URL if overwriting
        const prev = state.convertedItems.get(res.outRelPath);
        if (prev && prev.blobUrl) {
          URL.revokeObjectURL(prev.blobUrl);
        }

        state.convertedItems.set(res.outRelPath, {
          outFileName: res.outFileName,
          outRelPath: res.outRelPath,
          title: res.title || item.name.replace(/\.[^.]+$/, ""),
          size: epubBytes.byteLength,
          blobUrl,
          buffer: epubBytes,
        });

        const titleSuffix = res.title ? ` ('${res.title}')` : "";
        appendLog(`[OK] ${item.relPath} -> ${res.outFileName}${titleSuffix}`, "ok");
        renderDownloads();
      } else {
        failedCount++;
        const errType = (res.errorType || "failed").toUpperCase();
        const logClass =
          errType === "DRM" ? "drm" : errType === "CORRUPT" ? "corrupt" : "fail";
        appendLog(
          `[FAILED] ${item.relPath} [${errType}]: ${res.errorMessage || "Conversion failed"}`,
          logClass
        );
      }
    } catch (err) {
      failedCount++;
      if (total > 1) setProgress(idx, total, false);
      const msg = err && err.message ? err.message : String(err);
      appendLog(`[FAILED] ${item.relPath} [EXCEPTION]: ${msg}`, "fail");
    }
  }

  stopElapsedTimer();
  const elapsedSec = (performance.now() - state.startTime) / 1000;
  els.elapsedText.textContent = formatElapsed(elapsedSec);

  state.isRunning = false;
  setProgress(total, total, false);

  const summaryLine = `Summary: Converted: ${convertedCount}  |  Skipped: ${skippedCount}  |  Failed: ${failedCount}`;
  els.summaryText.textContent = summaryLine;

  if (state.cancelRequested) {
    els.statusText.textContent = `Stopped by user (${convertedCount} converted, ${skippedCount} skipped, ${failedCount} failed)`;
  } else {
    els.statusText.textContent = `Finished in ${elapsedSec.toFixed(1)}s`;
  }

  appendLog(`=== ${summaryLine} (Time: ${elapsedSec.toFixed(2)}s) ===`, "bold");
  updateControlsState();
  renderQueue();
}

// ---------------------------------------------------------------------------
// Downloads Rendering & ZIP Export
// ---------------------------------------------------------------------------

function renderDownloads() {
  const items = Array.from(state.convertedItems.values());
  els.convertedCountBadge.textContent = String(items.length);

  if (items.length === 0) {
    els.downloadsList.innerHTML =
      '<div class="empty-downloads">Converted EPUB files will appear here for instant download.</div>';
    els.btnDownloadAllZip.disabled = true;
    return;
  }

  els.downloadsList.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "download-item";

    const info = document.createElement("div");
    info.className = "download-info";

    const titleEl = document.createElement("div");
    titleEl.className = "download-title";
    titleEl.textContent = item.title || item.outFileName;

    const metaEl = document.createElement("div");
    metaEl.className = "download-meta";
    metaEl.textContent = `${item.outRelPath} · ${formatBytes(item.size)}`;

    info.appendChild(titleEl);
    info.appendChild(metaEl);

    const dlLink = document.createElement("a");
    dlLink.className = "btn btn-success btn-sm";
    dlLink.href = item.blobUrl;
    dlLink.download = item.outFileName;
    dlLink.textContent = "Download .epub";

    row.appendChild(info);
    row.appendChild(dlLink);
    els.downloadsList.appendChild(row);
  }

  els.btnDownloadAllZip.disabled = state.isRunning || items.length === 0;
}

async function handleDownloadAllZip() {
  const items = Array.from(state.convertedItems.values());
  if (items.length === 0) return;

  els.btnDownloadAllZip.disabled = true;
  const origText = els.btnDownloadAllZip.textContent;
  els.btnDownloadAllZip.textContent = "Building .zip...";

  try {
    const filesPayload = items.map((item) => ({
      name: item.outFileName,
      arcName: item.outRelPath,
      data: item.buffer.slice(0),
    }));

    const res = await callWorker({
      type: "create_zip",
      files: filesPayload,
    });

    if (res.success && res.zipData) {
      const blob = new Blob([res.zipData], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mobi2epub_converted_${items.length}_books.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      appendLog(`[OK] Downloaded ZIP archive with ${items.length} EPUB file(s).`, "ok");
    } else {
      appendLog(`[FAILED] Could not build ZIP archive: ${res.errorMessage || "Unknown error"}`, "fail");
    }
  } catch (err) {
    appendLog(`[FAILED] ZIP error: ${err && err.message ? err.message : String(err)}`, "fail");
  } finally {
    els.btnDownloadAllZip.textContent = origText;
    els.btnDownloadAllZip.disabled = state.isRunning || state.convertedItems.size === 0;
  }
}

// ---------------------------------------------------------------------------
// Try Sample MOBI
// ---------------------------------------------------------------------------

async function handleTrySample() {
  if (state.isRunning) return;
  try {
    els.statusText.textContent = "Loading bundled sample.mobi...";
    const resp = await fetch("./sample.mobi");
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} loading sample.mobi`);
    }
    const blob = await resp.blob();
    const sampleFile = new File([blob], "sample_mobi6.mobi", {
      type: "application/x-mobipocket-ebook",
    });

    // Enable overwrite for sample demo so clicking it multiple times always demonstrates conversion
    els.chkForce.checked = true;
    addFilesToQueue([{ file: sampleFile, relPath: "sample_mobi6.mobi" }], true);
    appendLog("[INFO] Loaded bundled sample book: sample_mobi6.mobi (Alice's Adventures in Wonderland).", "info");
    await startBatchConversion();
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    appendLog(`[FAILED] Could not load sample.mobi: ${message}`, "fail");
  }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

els.btnAddFiles.addEventListener("click", (e) => {
  e.stopPropagation();
  els.fileInput.value = "";
  els.fileInput.click();
});

els.btnSelectFolder.addEventListener("click", (e) => {
  e.stopPropagation();
  els.folderInput.value = "";
  els.folderInput.click();
});

els.btnTrySample.addEventListener("click", (e) => {
  e.stopPropagation();
  handleTrySample();
});

els.dropzone.addEventListener("click", (e) => {
  if (e.target === els.dropzone || e.target.closest(".dropzone-clickable")) {
    if (!state.isRunning) {
      els.fileInput.value = "";
      els.fileInput.click();
    }
  }
});

els.fileInput.addEventListener("change", () => {
  const files = Array.from(els.fileInput.files || []);
  if (files.length > 0) {
    addFilesToQueue(files.map((f) => ({ file: f, relPath: f.name })));
  }
});

els.folderInput.addEventListener("change", () => {
  const files = Array.from(els.folderInput.files || []);
  if (files.length > 0) {
    addFilesToQueue(
      files.map((f) => ({
        file: f,
        relPath: f.webkitRelativePath || f.name,
      }))
    );
  }
});

els.dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  if (!state.isRunning) {
    els.dropzone.classList.add("dragover");
  }
});

els.dropzone.addEventListener("dragleave", () => {
  els.dropzone.classList.remove("dragover");
});

els.dropzone.addEventListener("drop", async (e) => {
  e.preventDefault();
  els.dropzone.classList.remove("dragover");
  if (state.isRunning) return;

  const entries = await extractDroppedItems(e.dataTransfer);
  if (entries.length > 0) {
    addFilesToQueue(entries);
  }
});

els.btnClearQueue.addEventListener("click", clearQueue);
els.btnConvert.addEventListener("click", startBatchConversion);

els.btnCancel.addEventListener("click", () => {
  if (state.isRunning && !state.cancelRequested) {
    state.cancelRequested = true;
    els.btnCancel.textContent = "Stopping...";
    els.btnCancel.disabled = true;
    els.statusText.textContent = "Stopping after current file finishes...";
    appendLog("Cancellation requested: stopping after current file...", "info");
  }
});

els.btnClearLog.addEventListener("click", clearLog);
els.btnDownloadAllZip.addEventListener("click", handleDownloadAllZip);

// Start loading Pyodide worker immediately
initWorker();
