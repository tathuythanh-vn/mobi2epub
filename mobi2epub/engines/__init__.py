"""Engines package for mobi2epub."""

from __future__ import annotations

from typing import Dict, Type

from mobi2epub.engines.base import BaseEngine, EngineResult
from mobi2epub.engines.calibre import CalibreEngine
from mobi2epub.engines.kindleunpack import KindleUnpackEngine

ENGINES: dict[str, type[BaseEngine]] = {
    "kindleunpack": KindleUnpackEngine,
    "calibre": CalibreEngine,
}


def get_engine(name: str = "kindleunpack") -> BaseEngine:
    """Return an instance of the requested engine."""
    canonical = name.strip().lower()
    if canonical not in ENGINES:
        available = ", ".join(ENGINES.keys())
        raise ValueError(f"Unknown engine '{name}'. Available engines: {available}")
    return ENGINES[canonical]()
