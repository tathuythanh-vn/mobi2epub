# MOBI to EPUB Converter (MobiToEpub)

A fast, robust Kindle `.mobi` (`.prc`, `.azw3`, `.azw`) to standard `.epub` converter available as:
- **Browser Web App (GitHub Pages)**: [https://tathuythanh-vn.github.io/mobi2epub/](https://tathuythanh-vn.github.io/mobi2epub/) — 100% client-side in-browser conversion powered by Pyodide (WebAssembly) with zero server uploads.
- **Windows GUI Application (`MobiToEpub.exe`)**: [Download Latest Release (`MobiToEpub.exe`)](https://github.com/tathuythanh-vn/mobi2epub/releases/latest/download/MobiToEpub.exe)
- **Command-Line Interface (`mobi2epub.exe`)**: [Download CLI (`mobi2epub.exe`)](https://github.com/tathuythanh-vn/mobi2epub/releases/latest/download/mobi2epub.exe)

---

## Web App (100% Client-Side in Browser)

Launch the web converter directly at **[https://tathuythanh-vn.github.io/mobi2epub/](https://tathuythanh-vn.github.io/mobi2epub/)**:

- **Zero Server / Complete Privacy**: Runs our Python `mobi2epub` engine (`precheck.py`, `engines/kindleunpack.py`, `validate.py`) inside a browser Web Worker via Pyodide WebAssembly. Your books never leave your device.
- **Batch & Folder Support**: Drag-and-drop `.mobi`, `.prc`, `.azw3`, or `.azw` files, multi-select files, or select an entire folder.
- **One-Click Sample Test**: Click **"Try Sample MOBI"** to test the converter immediately in your browser.
- **Instant Download**: Download individual `.epub` files or batch-download all converted books as a `.zip` archive.

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
  - Bundled directly inside the executable. Unpacks MOBI6 and KF8/MOBI8 containers.
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

## 5. Running Automated Tests

```bash
pytest
```
34 automated tests covering pre-check, collector, engines, runner events, GUI smoke initialization, and EPUB validation.

---

## 6. GitHub Pages Deployment (`docs/`)

The static web application lives in `docs/` (`index.html`, `styles.css`, `app.js`, `worker.js`, `sample.mobi`, and bundled Python modules in `docs/py/`).

- **Automated CI/CD**: `.github/workflows/pages.yml` automatically deploys `docs/` to GitHub Pages on every push to `master`/`main`.
- **Live URL**: [https://tathuythanh-vn.github.io/mobi2epub/](https://tathuythanh-vn.github.io/mobi2epub/)
- **Local Preview**:
  ```bash
  python -m http.server 8000 --directory docs
  ```
  Then open `http://localhost:8000` in your browser.
