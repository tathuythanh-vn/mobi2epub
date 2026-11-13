"""Calibre conversion backend using ebook-convert CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from mobi2epub.engines.base import BaseEngine, EngineResult


def find_ebook_convert() -> Optional[Path]:
    """Find ebook-convert executable on system."""
    which_path = shutil.which("ebook-convert") or shutil.which("ebook-convert.exe")
    if which_path:
        return Path(which_path)

    # Windows standard paths
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Calibre2" / "ebook-convert.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Calibre2" / "ebook-convert.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Calibre2" / "ebook-convert.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c

    return None


class CalibreEngine(BaseEngine):
    """Conversion engine using Calibre's ebook-convert."""

    def __init__(self, binary_path: Optional[Path | str] = None):
        if binary_path is not None:
            self._binary: Optional[Path] = Path(binary_path)
        else:
            self._binary = find_ebook_convert()

    @property
    def name(self) -> str:
        return "calibre"

    def is_available(self) -> bool:
        return self._binary is not None and self._binary.exists()

    def convert(self, src: Path, dst: Path) -> EngineResult:
        if not self.is_available():
            return EngineResult(
                success=False,
                src_path=src,
                dst_path=dst,
                error_type="engine_unavailable",
                error_message="Calibre (ebook-convert) is not installed or not found in PATH",
            )

        src = src.resolve()
        dst = dst.resolve()

        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Use temporary file in destination directory for atomic write
        temp_fd, temp_file = tempfile.mkstemp(suffix=".epub", dir=dst.parent)
        os.close(temp_fd)
        temp_path = Path(temp_file)

        try:
            cmd = [str(self._binary), str(src), str(temp_path)]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            if proc.returncode != 0:
                output = (proc.stderr or proc.stdout).strip()
                lower_out = output.lower()
                if "drm" in lower_out or "encrypted" in lower_out:
                    return EngineResult(
                        success=False,
                        src_path=src,
                        dst_path=dst,
                        error_type="drm",
                        error_message="Calibre reported DRM protected book",
                    )
                return EngineResult(
                    success=False,
                    src_path=src,
                    dst_path=dst,
                    error_type="engine_error",
                    error_message=f"Calibre conversion failed (code {proc.returncode}): {output[:300]}",
                )

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                return EngineResult(
                    success=False,
                    src_path=src,
                    dst_path=dst,
                    error_type="engine_error",
                    error_message="Calibre completed but produced an empty or missing output file",
                )

            # Atomic replace
            temp_path.replace(dst)

            return EngineResult(
                success=True,
                src_path=src,
                dst_path=dst,
            )

        except Exception as e:
            return EngineResult(
                success=False,
                src_path=src,
                dst_path=dst,
                error_type="engine_error",
                error_message=f"Calibre execution error: {e}",
            )
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
