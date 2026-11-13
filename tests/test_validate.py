"""Tests for EPUB validator."""

import zipfile
from pathlib import Path

import pytest
from mobi2epub.validate import validate_epub


def test_validate_nonexistent():
    res = validate_epub("does_not_exist.epub")
    assert not res.is_valid
    assert "does not exist" in res.error_summary


def test_validate_not_a_zip(tmp_path: Path):
    bad = tmp_path / "bad.epub"
    bad.write_text("plain text, not zip")
    res = validate_epub(bad)
    assert not res.is_valid
    assert "not a valid zip" in res.error_summary.lower()


def test_validate_mimetype_must_be_first(tmp_path: Path):
    epub = tmp_path / "bad_order.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zf.writestr(zinfo, b"application/epub+zip")

    res = validate_epub(epub)
    assert not res.is_valid
    assert any("First entry in ZIP must be 'mimetype'" in e for e in res.errors)


def test_validate_mimetype_must_be_uncompressed(tmp_path: Path):
    epub = tmp_path / "compressed_mime.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("META-INF/container.xml", "<container/>")

    res = validate_epub(epub)
    assert not res.is_valid
    assert any("uncompressed" in e for e in res.errors)


def test_validate_valid_epub(tmp_path: Path):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")
    from mobi2epub.engines.kindleunpack import KindleUnpackEngine
    engine = KindleUnpackEngine()
    dst = tmp_path / "valid.epub"
    res = engine.convert(sample, dst)
    assert res.success

    val = validate_epub(dst)
    assert val.is_valid
    assert val.spine_items_count >= 1
    assert "Alice" in (val.title or "")
