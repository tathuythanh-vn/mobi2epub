"""Entry point for the GUI application (PyInstaller target)."""

import multiprocessing
import sys


class _NullStream:
    """Safe null stream for windowed frozen applications where stdout/stderr are None."""
    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass


if __name__ == "__main__":
    multiprocessing.freeze_support()

    # Guard against NoneType stdout/stderr in windowed exe
    if sys.stdout is None:
        sys.stdout = _NullStream()
    if sys.stderr is None:
        sys.stderr = _NullStream()

    from mobi2epub.gui import main
    main()
