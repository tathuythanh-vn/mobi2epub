"""Tests for MOBI pre-check: validation, corruption, and DRM detection."""

import struct
from pathlib import Path

import pytest
from mobi2epub.precheck import PrecheckResult, check_mobi_file


def test_precheck_nonexistent_file(tmp_path: Path):
    res = check_mobi_file(tmp_path / "does_not_exist.mobi")
    assert not res.is_valid
    assert "not found" in res.error_reason.lower()


def test_precheck_file_too_small(tmp_path: Path):
    small_file = tmp_path / "small.mobi"
    small_file.write_bytes(b"short bytes")
    res = check_mobi_file(small_file)
    assert not res.is_valid
    assert "too small" in res.error_reason.lower()


def test_precheck_invalid_magic(tmp_path: Path):
    corrupt_file = tmp_path / "bad_magic.mobi"
    # PalmDB header: 78 bytes with 1 record (8 bytes entry)
    header = bytearray(b"\x00" * 60)
    header += b"RAND" + b"JUNK"  # invalid type/creator
    header += struct.pack(">IIH", 0, 0, 1)  # seed, next_id, num_records=1
    rec0_offset = 86
    header += struct.pack(">IB3s", rec0_offset, 0, b"\x00\x00\x00")
    # Record 0 (compression=1, no MOBI magic)
    rec0 = struct.pack(">HHIIHH", 1, 0, 10, 1, 4096, 0) + b"\x00" * 50
    corrupt_file.write_bytes(bytes(header) + rec0)

    res = check_mobi_file(corrupt_file)
    assert not res.is_valid
    assert "not a mobi" in res.error_reason.lower()


def test_precheck_valid_mobi6():
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")
    res = check_mobi_file(sample)
    assert res.is_valid
    assert not res.is_drm
    assert res.version == 6
    assert "Alice" in (res.title or "")


def test_precheck_drm_detection():
    drm_file = Path("tests/fixtures/drm_protected.mobi")
    if not drm_file.exists():
        pytest.skip("drm_protected.mobi not available")
    res = check_mobi_file(drm_file)
    assert res.is_valid
    assert res.is_drm
    assert not res.can_convert
    assert "drm" in (res.error_reason or "").lower()
