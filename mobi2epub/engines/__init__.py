"""Engines package for mobi2epub with lazy backend loading."""

from __future__ import annotations

from typing import List
from mobi2epub.engines.base import BaseEngine, EngineResult

AVAILABLE_ENGINES = ["kindleunpack", "calibre"]
ENGINES = AVAILABLE_ENGINES


def get_engine(name: str = "kindleunpack") -> BaseEngine:
    """Return an instance of the requested engine, importing backends lazily."""
    canonical = name.strip().lower()
    if canonical == "kindleunpack":
        from mobi2epub.engines.kindleunpack import KindleUnpackEngine
        return KindleUnpackEngine()
    elif canonical == "calibre":
        from mobi2epub.engines.calibre import CalibreEngine
        return CalibreEngine()
    else:
        available_str = ", ".join(AVAILABLE_ENGINES)
        raise ValueError(f"Unknown engine '{name}'. Available engines: {available_str}")
