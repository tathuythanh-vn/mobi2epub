# Web App Feature Roadmap & Implementation Plan (`plan.md`)

This document outlines the roadmap to upgrade the **MobiToEpub Static Web Application** (`docs/`, hosted on GitHub Pages at https://tathuythanh-vn.github.io/mobi2epub/) with **17 client-side features** plus **Web App Unit Tests & CI**.

All features are designed to run **100% in the user's browser** (WebAssembly / Pyodide + Browser Web APIs) with zero backend server required.

---

## Phase 1: Performance, Offline PWA & Storage

### 1. Offline PWA + Instant Load (`Service Worker` + `manifest.webmanifest`)
- **Goal**: Drop repeat-visit startup time from ~3–5s to **<0.3s**, allow **100% offline usage**, and make the web app installable on desktop/mobile.
- **Implementation**:
  - Create `docs/manifest.webmanifest` with app metadata, icons (`app_icon.ico` / PNG icons), and `display: "standalone"`.
  - Create `docs/sw.js` (Service Worker) using a cache-first strategy for Pyodide CDN assets (`pyodide.asm.wasm`, `pyodide.asm.js`, `python_stdlib.zip`, `beautifulsoup4`, `soupsieve`) and stale-while-revalidate for local app shell files (`index.html`, `app.js`, `worker.js`, `styles.css`, `py/bundle.zip`).
  - Register the Service Worker in `docs/app.js` and add an **"Install App"** button in the header when `beforeinstallprompt` fires.

### 2. Multi-Worker Parallel Conversion Pool
- **Goal**: Convert large batches (10–100+ books) **3–4× faster** on multi-core CPUs.
- **Implementation**:
  - Replace the single Web Worker in `docs/app.js` with a dynamic `WorkerPool` sized to `Math.min(navigator.hardwareConcurrency || 2, 4, totalFiles)`.
  - For single-file runs, spin up 1 worker; for multi-file batches, distribute queued files across idle workers in natural sort order while aggregating progress events into the main UI.

### 3. Direct "Save to Folder" (File System Access API)
- **Goal**: Let Chrome/Edge/Opera users write converted `.epub` files directly into a chosen local disk folder (mirroring subfolders) without downloading a `.zip`.
- **Implementation**:
  - Detect `'showDirectoryPicker' in window`.
  - Add an optional **"Choose Output Folder (Direct Save)"** button.
  - When set, as each book finishes converting, create subdirectories via `dirHandle.getDirectoryHandle(part, { create: true })` and write the `.epub` bytes via `fileHandle.createWritable()`.

### 4. Browser History Cache (`IndexedDB` — "Recent Conversions")
- **Goal**: Prevent lost work if the user refreshes or closes the tab after converting a batch.
- **Implementation**:
  - Store recent converted `.epub` blobs, metadata, and timestamps in an `IndexedDB` store (`mobi2epub_history`, capped at e.g. last 20 books or 100 MB with a **"Clear History"** button).
  - Render a collapsible **"Recent Conversions"** section on page load so previously converted books can be downloaded immediately.

---

## Phase 2: Rich Book Cards, Previews & Inspection

### 5. Book Cover, Title & Metadata Cards
- **Goal**: Show visual book cards instead of plain filenames in the results list.
- **Implementation**:
  - In `docs/worker.js`, extract the cover image bytes (from OPF `<meta name="cover">` or manifest cover item), `<dc:title>`, `<dc:creator>`, `<dc:language>`, and file size during conversion.
  - Return a Base64/Blob URL thumbnail alongside the `.epub` bytes and render a book card with Cover Thumbnail, Title, Author, Original -> Output Size, and action buttons.

### 6. Built-in In-Browser EPUB Reader Preview
- **Goal**: Let users inspect and read a converted `.epub` right inside the page before downloading.
- **Implementation**:
  - Add a **"Preview / Read"** button on each converted book card.
  - Open a modal reader view that parses the `.epub` spine and renders chapters inside a sandboxed `<iframe>` with Previous/Next chapter navigation, TOC sidebar, and font-size controls.

### 7. EPUB Structure & Health Report Badge
- **Goal**: Give transparent verification details for every converted book.
- **Implementation**:
  - Extend `validate_epub()` in `docs/worker.js` to return a structured diagnostics object:
    - EPUB Version (`2.0` vs `3.0`)
    - Spine item count & total XHTML size
    - Image count & embedded font count
    - TOC entry count (`toc.ncx` / `nav.xhtml`)
    - Validation checklist (`mimetype` uncompressed first, `container.xml` valid, OPF valid, all spine targets present).
  - Clicking the `[VALID EPUB]` badge opens a popover with the health report.

### 8. Table of Contents (TOC) Inspector & Editor
- **Goal**: View and fix the book's internal Table of Contents before downloading.
- **Implementation**:
  - Parse `toc.ncx` / `nav.xhtml` into a JSON tree and display it in a collapsible drawer per book.
  - Allow renaming chapter titles, reordering entries, or hiding empty/duplicate entries, and re-pack `toc.ncx` / `nav.xhtml` in the worker on save.

---

## Phase 3: Customization & Book Optimization

### 9. Edit Metadata & Cover Before Download
- **Goal**: Fix missing/wrong book titles, authors, or covers in the browser.
- **Implementation**:
  - Add an **"Edit Metadata"** modal for queued or converted items with fields for:
    - `Title`, `Author`, `Language`, `Publisher`, `Description`
    - Custom Cover upload (`.jpg` / `.png` file picker or drag-and-drop)
  - Update `<metadata>` in `content.opf` and replace the cover image in the EPUB archive.

### 10. Custom Output Filename Templates
- **Goal**: Automatically name `.epub` files using book metadata.
- **Implementation**:
  - Add a filename template selector in Options:
    - `{OriginalFilename}.epub` (default)
    - `{Title}.epub`
    - `{Author} - {Title}.epub`
    - `{Title} ({Language}).epub`
  - Sanitize illegal filesystem characters (`/ \ : * ? " < > |`) and deduplicate colliding names automatically.

### 11. Custom CSS / Typography Injection
- **Goal**: Improve reading aesthetics on e-readers with optional typography presets.
- **Implementation**:
  - Add a **"Typography Preset"** dropdown in Options:
    - *Keep Original Styling* (default)
    - *Clean Book Serif* (comfortable line-height `1.5`, justified text, clean margins)
    - *Modern Sans-Serif*
    - *Dyslexia-Friendly* (wider letter/word spacing, left-aligned)
  - Inject a `custom-theme.css` into the EPUB manifest and link it in all XHTML spine documents.

### 12. Auto-Split Large HTML Chapters
- **Goal**: Make old MOBI6 books render and turn pages much faster on e-ink devices (Kobo, Nook, older Kindles).
- **Implementation**:
  - Add an **"Auto-split large chapters"** checkbox (enabled by default for MOBI6 files > 200 KB).
  - In Python (`kindleunpack.py` / worker), split `book.xhtml` at `<div class="mbp_pagebreak">` or top-level `<h1>`/`<h2>` boundaries into `part001.xhtml`, `part002.xhtml`, ..., update internal `#filepos` anchor links across files, and update `<manifest>` and `<spine>` in `content.opf`.

### 13. Image Compression & E-Ink Grayscale Optimizer
- **Goal**: Shrink image-heavy `.epub` files by 50–70%.
- **Implementation**:
  - Add an optional **"Optimize images"** setting with controls for Max Dimension (e.g., `1200px`), JPEG Quality (`75%`), and an **"E-Ink Grayscale"** toggle.
  - Process extracted images using `OffscreenCanvas` in the Web Worker before packaging the `.epub` ZIP.

---

## Phase 4: Input/Output Convenience & UX Polish

### 14. Drop a `.zip` Archive of `.mobi` Books
- **Goal**: Allow users to drop a single `.zip` containing an entire folder of `.mobi` books.
- **Implementation**:
  - Accept `.zip` files in the dropzone and file picker.
  - Unpack the `.zip` in the worker using Python's `zipfile`, extract all `.mobi`/`.prc`/`.azw3`/`.azw` entries (preserving internal folder paths), convert each to `.epub`, and bundle them into the output `.zip`.

### 15. Mobile "Share / Open In..." (Web Share API)
- **Goal**: One-tap export to Apple Books, Google Play Books, or Kindle on iOS/Android.
- **Implementation**:
  - Detect `navigator.canShare && navigator.canShare({ files: [epubFile] })`.
  - Show a **"Share / Open In..."** button on mobile devices that invokes `navigator.share({ files: [epubFile], title: bookTitle })`.

### 16. Dark / Light Theme Toggle
- **Goal**: Comfortable daytime and nighttime usage.
- **Implementation**:
  - Define CSS custom variables (`--bg`, `--surface`, `--text`, `--border`, `--accent`) for `[data-theme="light"]` and `[data-theme="dark"]` in `docs/styles.css`.
  - Default to `window.matchMedia('(prefers-color-scheme: dark)')` with a header toggle button saved in `localStorage`.

### 17. Multi-Language UI (`i18n` — English & Vietnamese)
- **Goal**: Native localized interface for both English and Vietnamese users.
- **Implementation**:
  - Create a lightweight `i18n` dictionary (`en` / `vi`) in `docs/app.js` with `data-i18n` attributes on static DOM elements and formatted status/log strings.
  - Add an `EN | VI` language switch in the top navigation bar (persisted in `localStorage`).

---

## Phase 5: Automated Web App Unit Tests & CI

### 18. Web App Test Suite (`tests/test_webapp.py`) & GitHub Actions CI (`.github/workflows/ci.yml`)
- **Goal**: Ensure the web app bundle, worker scripts, and core Python engine stay 100% tested on every commit.
- **Implementation**:
  - Add `tests/test_webapp.py` to test:
    - `docs/py/bundle.zip` integrity and parity with `mobi2epub/` source files.
    - Isolated end-to-end conversion of `sample_mobi6.mobi`, `corrupt.mobi`, and `drm_protected.mobi` using `docs/py/bundle.zip`.
    - Relative path verification in `docs/index.html`, `docs/app.js`, and `docs/worker.js` for GitHub Pages subpath compatibility.
    - JavaScript syntax check (`node --check`) for all `.js` files in `docs/`.
  - Add `.github/workflows/ci.yml` to run `pytest` on every push and pull request before deploying to GitHub Pages.

---

## Suggested Implementation Order (Milestones)

| Milestone | Features Included | Priority |
|---|---|---|
| **M1 — UX & Polish** | #16 Dark Mode, #17 EN/VI Language Toggle, #10 Filename Templates, #18 Web App Tests & CI | High (Fast wins) |
| **M2 — Rich Output & Preview** | #5 Cover & Metadata Cards, #7 EPUB Health Badge, #6 Built-in EPUB Reader Preview | High (Best visual impact) |
| **M3 — Speed & Offline PWA** | #1 Offline Service Worker PWA, #2 Multi-Worker Pool, #4 IndexedDB History, #3 Direct Save to Folder | High (Performance) |
| **M4 — Power Editing & Optimization** | #9 Metadata/Cover Editor, #8 TOC Editor, #11 Custom CSS Presets, #12 Auto-Split Chapters, #13 Image Optimizer, #14 ZIP Input, #15 Mobile Share | Medium (Power-user tools) |
