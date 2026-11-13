# mobi2epub

A fast, robust command-line tool to convert Kindle `.mobi` books into standard `.epub` files.

## Features

- **1:1 Conversion**: One EPUB per input MOBI file. Each book preserves its internal table of contents, metadata, and images.
- **Pure Python Default**: Uses `KindleUnpack` via the `mobi` package by default—no external dependencies or large software installations required.
- **Optional Calibre Backend**: Switch to Calibre's `ebook-convert` with `--engine calibre`.
- **Pre-check Validation**: Inspects MOBI and PalmDOC headers before unpacking, detecting DRM encryption and corrupt files cleanly and early.
- **Directory Mirroring & Natural Sorting**: Processes single files or entire folders with `--recursive`, naturally sorting numbers (e.g., `book1`, `book2`, `book10`) and mirroring subfolder hierarchies in the destination folder.
- **Safe & Atomic Writes**: Outputs to temporary files first and renames on completion, ensuring half-written files are never left behind if interrupted.
- **Progress & Summary Tracking**: Real-time `tqdm` progress bar on `stderr` (auto-hidden for single files or with `--quiet`), followed by a detailed summary report.
- **Parallel Processing**: Speed up large batch conversions using `--jobs N` with Python's `ProcessPoolExecutor`.
- **Unicode & Cross-Platform**: Full support for Unicode characters (e.g. Vietnamese titles/filenames), long paths, Windows, macOS, and Linux.

---

## Installation

```bash
# Clone or navigate to the directory
cd converter

# Install locally in editable mode
pip install -e .
```

Or install with [pipx](https://pypa.github.io/pipx/):

```bash
pipx install .
```

---

## CLI Usage

```text
mobi2epub <input> [-o OUTPUT_DIR] [--recursive] [--force] [--quiet] [--engine {kindleunpack,calibre}] [--jobs N]
```

### Arguments & Options

| Option | Description |
|---|---|
| `<input>` | A `.mobi` file or a directory containing `.mobi` files. |
| `-o, --output` | Destination directory. Default is next to the input file, or current directory for folder input. |
| `-r, --recursive` | Search subdirectories recursively and mirror the folder structure in the output directory. |
| `-f, --force` | Overwrite existing EPUB files. Default behavior is to skip them and report. |
| `-q, --quiet` | Suppress progress bars and non-essential summary logs. |
| `--engine` | Engine backend: `kindleunpack` (default) or `calibre`. |
| `-j, --jobs` | Number of concurrent worker processes for parallel conversion (default: `1`). |

---

## Examples

### 1. Convert a single book
```bash
mobi2epub novel.mobi
# Creates novel.epub next to novel.mobi
```

### 2. Convert to a specific output folder
```bash
mobi2epub novel.mobi -o ~/Books/
# Creates ~/Books/novel.epub
```

### 3. Convert an entire folder with subfolders (mirrored structure)
```bash
mobi2epub ~/KindleLibrary/ -o ~/EpubLibrary/ --recursive
```
If `~/KindleLibrary/` contains:
```text
KindleLibrary/
├── Fantasy/
│   └── Book1.mobi
└── SciFi/
    └── Dune.mobi
```
`~/EpubLibrary/` will contain:
```text
EpubLibrary/
├── Fantasy/
│   └── Book1.epub
└── SciFi/
    └── Dune.epub
```

### 4. Overwrite existing files and speed up with 4 parallel jobs
```bash
mobi2epub ~/KindleLibrary/ -o ~/EpubLibrary/ --force --jobs 4
```

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | All files succeeded (or were skipped without errors). |
| `1` | One or more files failed conversion (e.g. DRM-protected, corrupt). |
| `2` | Nothing could run (invalid arguments, input path does not exist, no `.mobi` files found). |

---

## Project Structure

```text
mobi2epub/
├── __init__.py
├── __main__.py        # Supports: python -m mobi2epub
├── cli.py             # argparse, entry point, process orchestration
├── collector.py       # find .mobi files, natural sort, directory mirroring
├── precheck.py        # PalmDOC/MOBI header parsing, DRM check, corrupt detection
├── progress.py        # tqdm progress tracking and summary reporting
├── validate.py        # EPUB verification (ZIP, mimetype, container.xml, OPF, spine)
├── engines/
│   ├── base.py        # Engine interface (BaseEngine, EngineResult)
│   ├── kindleunpack.py# Pure-Python KindleUnpack backend (default)
│   └── calibre.py     # Subprocess Calibre ebook-convert backend (optional)
└── tests/             # Comprehensive pytest suite
```

---

## Running Tests

```bash
pytest
```
