# MOBI to EPUB Converter (MobiToEpub)

A fast, robust Kindle `.mobi` (`.prc`, `.azw3`, `.azw`) to standard `.epub` converter available as:
- **Browser Web App (GitHub Pages / Offline PWA)**: [https://tathuythanh-vn.github.io/mobi2epub/](https://tathuythanh-vn.github.io/mobi2epub/) — 100% client-side in-browser conversion powered by Pyodide (WebAssembly) with zero server uploads.
- **Windows GUI Application (`MobiToEpub.exe`)**: [Download Latest Release (`MobiToEpub.exe`)](https://github.com/tathuythanh-vn/mobi2epub/releases/latest/download/MobiToEpub.exe)
- **Command-Line Interface (`mobi2epub.exe`)**: [Download CLI (`mobi2epub.exe`)](https://github.com/tathuythanh-vn/mobi2epub/releases/latest/download/mobi2epub.exe)

---

## Web App (100% Client-Side in Browser)

Launch the web converter directly at **[https://tathuythanh-vn.github.io/mobi2epub/](https://tathuythanh-vn.github.io/mobi2epub/)**:

### Core Highlights
- **Zero Server / Complete Privacy**: Runs our Python `mobi2epub` engine (`precheck.py`, `engines/kindleunpack.py`, `validate.py`) inside browser Web Workers via Pyodide WebAssembly. Your books never leave your device.
- **One-Click Sample Test**: Click **"Try Sample MOBI"** to test the converter immediately in your browser.
- **Instant Download**: Download individual `.epub` files, write directly to a local folder, or batch-download all converted books as a `.zip` archive.

### All 17 Web App Features
1. **Offline PWA + Instant Load (`Service Worker` + `manifest.webmanifest`)**: Caches the Pyodide WebAssembly runtime and app shell locally so repeat visits load in **<0.3s**, work **100% offline**, and can be installed as a standalone desktop/mobile app.
2. **Multi-Worker Parallel Conversion Pool**: Dynamically scales across CPU cores (`WorkerPool` up to 4 parallel Web Workers) to convert multi-book batches 3–4× faster without blocking the UI.
3. **Direct "Save to Folder" (File System Access API)**: On Chromium browsers (Chrome, Edge, Opera), write converted `.epub` files directly into a chosen local folder (mirroring subfolder structure) without downloading a `.zip`.
4. **Browser History Cache (`IndexedDB` — "Recent Conversions")**: Automatically preserves up to 20 recently converted `.epub` books in `IndexedDB` (`mobi2epub_history`) so work is never lost on tab refresh, with one-click Download, Preview, and Clear History.
5. **Book Cover, Title & Metadata Cards**: Extracts cover thumbnails, `<dc:title>`, `<dc:creator>`, `<dc:language>`, and file size comparisons (`MOBI -> EPUB`) into rich visual book cards.
6. **Built-in In-Browser EPUB Reader Preview**: Read and inspect converted `.epub` books right inside the browser in a sandboxed `<iframe>` modal with chapter navigation, TOC sidebar, and `A-`/`A+` font-size controls.
7. **EPUB Structure & Health Report Badge**: Interactive `[VALID EPUB]` badge displaying a full diagnostic breakdown: EPUB version (`2.0`/`3.0`), spine count, total XHTML size, image count, embedded font count, TOC count, and structural validation checks (`mimetype` uncompressed first, valid `container.xml`, valid `content.opf`, all spine targets present).
8. **Table of Contents (TOC) Inspector & Editor**: Inspect `toc.ncx` / `nav.xhtml` entries, rename chapter titles, or remove unwanted TOC items before downloading.
9. **Live Metadata & Cover Editor**: Edit Title, Author, Language, Publisher, Description, and upload a custom `.jpg`/`.png` cover image before or after conversion—re-packing the `.epub` in `<0.1s`.
10. **Custom Output Filename Templates**: Automatically format output filenames using book metadata: `{OriginalFilename}.epub`, `{Title}.epub`, `{Author} - {Title}.epub`, or `{Title} ({Language}).epub`.
11. **Custom CSS / Typography Injection**: Inject clean reading stylesheets into converted EPUBs with presets for *Keep Original Styling*, *Clean Book Serif*, *Modern Sans-Serif*, and *Dyslexia-Friendly*.
12. **Auto-Split Large HTML Chapters**: Splits monolithic MOBI6 HTML books at `<div class="mbp_pagebreak">` or `<h1>`/`<h2>` boundaries into `part001.xhtml`, `part002.xhtml`, ... while rewriting cross-part `#filepos` links for fast page turns on e-ink devices.
13. **Image Compression & E-Ink Grayscale Optimizer**: Resizes large book images, compresses JPEGs, and optionally converts images to E-Ink grayscale using `OffscreenCanvas` in the Web Worker.
14. **Drop a `.zip` Archive of `.mobi` Books**: Drag and drop a `.zip` archive containing `.mobi`, `.prc`, `.azw3`, or `.azw` files to automatically extract and queue every ebook inside.
15. **Mobile "Share / Open In..." (Web Share API)**: One-tap export of converted `.epub` files to Apple Books, Google Play Books, or Kindle on iOS and Android devices.
16. **Dark / Light Theme Toggle**: Respects system `prefers-color-scheme` with a header `🌙 / ☀️` toggle persisted in `localStorage`.
17. **Multi-Language UI (`EN | VI`)**: Instant English and Vietnamese interface localization (`EN | VI` switch in the header).

---

## Download & Portable Run (Windows Desktop)

**`dist/MobiToEpub.exe`** is a standalone, single-file Windows executable (no Python or external dependencies required), available on the [GitHub Releases](https://github.com/tathuythanh-vn/mobi2epub/releases/latest) page.

### Windows Delivery Note:
- If Windows SmartScreen shows *"Windows protected your PC"*, click **"More info"** and then **"Run anyway"**.
- Allow a few seconds for the single-file executable to unpack its runtime on the first launch.

---

## 1. Graphical User Interface (GUI)

Launch `dist/MobiToEpub.exe` (or run `python gui_main.py`):

![MobiToEpub GUI](app_icon.ico)

### Features & Layout:
- **Input Selection**:
  - **"Add files..."**: Multi-select individual `.mobi`, `.azw3`, `.prc` files.
  - **"Select folder..."**: Select a folder containing ebooks.
- **Required Output Folder**:
  - The **"Convert"** button remains safely disabled until a valid, writable output directory is selected.
- **Options**:
  - **Include subfolders**: Recursively scans directories and mirrors the folder structure in the output destination.
  - **Overwrite existing**: When unchecked, existing EPUBs are safely skipped and reported.
- **Progress Tracking**:
  - Determinate progress bar for batches, showing `12 / 50 · book.mobi` and elapsed time.
  - Switches to smooth indeterminate animation for single-file conversions.
- **Live Activity Log**:
  - Color-coded log tagging `[OK]`, `[SKIPPED]`, `[FAILED]`, and `[DRM]` with clear root-cause explanations.
- **Cancellation**:
  - **"Cancel"** stops conversion safely after the current file finishes, ensuring no corrupt or half-written EPUBs remain.
- **Summary & Open Folder**:
  - Final counts for converted, skipped, and failed books.
  - **"Open output folder"** button opens the destination directly in Windows File Explorer.

---

## 2. Command-Line Interface (CLI)

Run `dist/mobi2epub.exe` (or `python -m mobi2epub`):

```bash
mobi2epub <input> [-o OUTPUT_DIR] [--recursive] [--force] [--quiet] [--engine {kindleunpack,calibre}] [--jobs N]
```

### Options:
| Option | Description |
|---|---|
| `<input>` | A `.mobi` file or a directory containing `.mobi` files. |
| `-o, --output` | Destination directory (defaults to input file's directory or current working directory). |
| `-r, --recursive` | Search subdirectories recursively and mirror the folder structure in the output. |
| `-f, --force` | Overwrite existing EPUB files. Default behavior is to skip them. |
| `-q, --quiet` | Suppress progress bars and non-essential summary logs. |
| `--engine` | Conversion engine backend: `kindleunpack` (default) or `calibre` (optional). |
| `-j, --jobs` | Number of concurrent workers for parallel batch conversion (CLI only). |

### CLI Examples:
```bash
# Convert a single book
mobi2epub novel.mobi

# Convert an entire library folder recursively to a new folder
mobi2epub C:\KindleBooks -o C:\EpubLibrary --recursive

# Convert with 4 parallel jobs and overwrite existing files
mobi2epub C:\KindleBooks -o C:\EpubLibrary --force --jobs 4
```

---

## 3. Architecture & Engine

- **Work/Display Separation (`mobi2epub/runner.py`)**:
  - Central `run_batch(inputs, out_dir, options, on_event, cancel_event) -> BatchSummary`.
  - GUI and CLI share the exact same conversion, pre-check, and validation core.
  - When `jobs == 1` (always in GUI), execution runs entirely in-process with **zero spawned processes**.
  - Worker thread + thread-safe `queue.Queue` ensures the GUI window never freezes.
- **Pure Python Engine (KindleUnpack)**:
  - Bundled directly inside the executable and `docs/py/bundle.zip`. Unpacks MOBI6 and KF8/MOBI8 containers.
  - Builds standards-compliant EPUBs with uncompressed `mimetype` first, `META-INF/container.xml`, `content.opf`, `toc.ncx`, and valid XHTML content.
- **Pre-check & DRM Detection (`mobi2epub/precheck.py`)**:
  - Reads binary headers at offset to detect corrupt files and DRM-encrypted books early.
- **Calibre Backend (`mobi2epub/engines/calibre.py`)**:
  - Loaded lazily only when `--engine calibre` is invoked via CLI.

---

## 4. Building Executables with PyInstaller

Run the automated build script:

```cmd
build.bat
```

This installs pinned dependencies from `requirements.txt`, runs `PyInstaller mobi2epub.spec`, and outputs:
- `dist/MobiToEpub.exe` (Windowed GUI, ~12 MB)
- `dist/mobi2epub.exe` (Console CLI, ~12 MB)

---

## 5. Automated Test Suite & GitHub Actions CI

```bash
pytest -v
```

- **Desktop & Core Engine Tests (`tests/test_*.py`)**: 34 unit and integration tests covering binary header pre-check, file collector, KindleUnpack & Calibre engines, runner batch events, GUI smoke initialization, and EPUB structure validation.
- **Web App Test Suite (`tests/test_webapp.py`)**: Automated tests verifying `docs/py/bundle.zip` integrity, `docs/py/manifest.json` completeness, PWA `docs/manifest.webmanifest` schema & icons, `node --check` JavaScript syntax validation (`docs/app.js`, `docs/worker.js`, `docs/sw.js`), GitHub Pages relative path compliance, and isolated end-to-end Python web worker features (metadata/cover extraction, EPUB health report, TOC extraction & override, metadata/cover live override, custom CSS preset injection, chapter auto-splitting, and input `.zip` extraction).
- **Continuous Integration (`.github/workflows/ci.yml`)**: Automatically runs `pytest -v` and `node --check` on Python 3.12 + Node 20 on every push and pull request to `master`/`main`.

---

## 6. GitHub Pages Deployment (`docs/`)

The static web application lives in `docs/` (`index.html`, `styles.css`, `app.js`, `worker.js`, `sw.js`, `manifest.webmanifest`, `sample.mobi`, and bundled Python modules in `docs/py/`).

- **Automated CI/CD**: `.github/workflows/pages.yml` automatically deploys `docs/` to GitHub Pages on every push to `master`/`main`.
- **Live URL**: [https://tathuythanh-vn.github.io/mobi2epub/](https://tathuythanh-vn.github.io/mobi2epub/)
- **Local Preview**:
  ```bash
  python -m http.server 8000 --directory docs
  ```
  Then open `http://localhost:8000` in your browser.
