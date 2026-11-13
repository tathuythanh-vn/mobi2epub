"""Abstract base class for MOBI to EPUB conversion engines."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EngineResult:
    success: bool
    src_path: Path
    dst_path: Path
    error_message: Optional[str] = None
    error_type: Optional[str] = None  # "drm", "corrupt", "engine_error", etc.
    title: Optional[str] = None


class BaseEngine(abc.ABC):
    """Common interface for MOBI to EPUB conversion backends."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the engine."""
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check whether this engine is installed and ready to use."""
        pass

    @abc.abstractmethod
    def convert(self, src: Path, dst: Path) -> EngineResult:
        """Convert a MOBI file at src to an EPUB file at dst.

        Must write atomically to dst (e.g. using a temp file and rename).
        """
        pass
