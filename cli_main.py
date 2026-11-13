"""Entry point for the CLI application (PyInstaller target)."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from mobi2epub.cli import main
    sys.exit(main())
