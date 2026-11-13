"""Tests for conversion engines and factory."""

from pathlib import Path

import pytest
from mobi2epub.engines import ENGINES, get_engine
from mobi2epub.engines.calibre import CalibreEngine
from mobi2epub.engines.kindleunpack import KindleUnpackEngine


def test_get_engine_factory():
    ku = get_engine("kindleunpack")
    assert isinstance(ku, KindleUnpackEngine)
    assert ku.name == "kindleunpack"
    assert ku.is_available()

    cal = get_engine("calibre")
    assert isinstance(cal, CalibreEngine)
    assert cal.name == "calibre"

    with pytest.raises(ValueError, match="Unknown engine"):
        get_engine("non_existent_engine")


def test_kindleunpack_convert_sample(tmp_path: Path):
    src = Path("tests/fixtures/sample_mobi6.mobi")
    if not src.exists():
        pytest.skip("sample_mobi6.mobi not available")

    dst = tmp_path / "test_out.epub"
    engine = KindleUnpackEngine()
    res = engine.convert(src, dst)

    assert res.success
    assert dst.exists()
    assert dst.stat().st_size > 0
    assert "Alice" in (res.title or "")


def test_calibre_unavailable_reports_error(tmp_path: Path):
    engine = CalibreEngine(binary_path="/non/existent/ebook-convert")
    assert not engine.is_available()

    src = tmp_path / "book.mobi"
    dst = tmp_path / "book.epub"
    res = engine.convert(src, dst)

    assert not res.success
    assert res.error_type == "engine_unavailable"
