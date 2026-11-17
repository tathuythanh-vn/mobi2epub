"""MOBI file pre-check: header validation, corrupt file detection, and DRM checks."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PrecheckResult:
    is_valid: bool
    is_drm: bool = False
    error_reason: Optional[str] = None
    title: Optional[str] = None
    version: Optional[int] = None
    crypto_type: int = 0

    @property
    def can_convert(self) -> bool:
        return self.is_valid and not self.is_drm


def check_mobi_file(path: str | Path) -> PrecheckResult:
    """Read the MOBI file header to verify format, corruption, and DRM status.

    Detects:
      - Missing or unreadable files
      - Files too small or truncated
      - Non-MOBI / Non-PalmDOC files
      - DRM encrypted files (crypto_type != 0)
    """
    file_path = Path(path)

    if not file_path.exists():
        return PrecheckResult(is_valid=False, error_reason="File not found")

    try:
        file_size = file_path.stat().st_size
    except OSError as e:
        return PrecheckResult(is_valid=False, error_reason=f"Cannot access file: {e}")

    if file_size < 78:
        return PrecheckResult(is_valid=False, error_reason="File too small (< 78 bytes, corrupt header)")

    try:
        with open(file_path, "rb") as f:
            # Read first 4KB which covers PDB header and start of Record 0 in virtually all files
            header_data = f.read(min(file_size, 4096))
    except OSError as e:
        return PrecheckResult(is_valid=False, error_reason=f"Cannot read file: {e}")

    if len(header_data) < 78:
        return PrecheckResult(is_valid=False, error_reason="Truncated file header")

    # Palm Database Header
    db_name = header_data[0:32].split(b"\x00")[0].decode("latin-1", errors="replace")
    magic_type = header_data[60:64]
    magic_creator = header_data[64:68]
    (num_records,) = struct.unpack_from(">H", header_data, 76)

    if num_records == 0:
        return PrecheckResult(is_valid=False, error_reason="Corrupt PalmDOC: 0 records")

    # Each record entry in the table is 8 bytes: 4 bytes offset, 1 byte attrs, 3 bytes unique ID
    record_table_size = 78 + (num_records * 8)
    if file_size < record_table_size:
        return PrecheckResult(is_valid=False, error_reason="Corrupt file: record table truncated")

    (rec0_offset,) = struct.unpack_from(">I", header_data, 78)

    if rec0_offset >= file_size:
        return PrecheckResult(is_valid=False, error_reason="Corrupt file: record 0 offset points beyond file end")

    # Read Record 0 if it was beyond initial 4KB buffer
    if rec0_offset + 128 > len(header_data):
        try:
            with open(file_path, "rb") as f:
                f.seek(rec0_offset)
                rec0_data = f.read(2048)
        except OSError as e:
            return PrecheckResult(is_valid=False, error_reason=f"Error reading record 0: {e}")
    else:
        rec0_data = header_data[rec0_offset:]

    if len(rec0_data) < 16:
        return PrecheckResult(is_valid=False, error_reason="Corrupt file: record 0 header is truncated")

    # Check compression: 1=None, 2=PalmDoc, 0x4448=Huff/CDIC
    (compression,) = struct.unpack_from(">H", rec0_data, 0)
    if compression not in (1, 2, 0x4448):
        return PrecheckResult(
            is_valid=False,
            error_reason=f"Unsupported or corrupt compression: 0x{compression:04x}",
        )

    # Check for MOBI identifier at offset 16
    has_mobi_magic = len(rec0_data) >= 20 and rec0_data[16:20] == b"MOBI"
    is_palm_doc = magic_creator == b"REAd" or magic_type == b"TEXt"
    is_mobi = magic_creator == b"MOBI" or magic_type == b"BOOK" or has_mobi_magic

    if not is_mobi and not is_palm_doc:
        return PrecheckResult(
            is_valid=False,
            error_reason=f"Not a MOBI/Kindle file (type: {magic_type!r}, creator: {magic_creator!r})",
        )

    crypto_type = 0
    version = None
    title = db_name

    # Crypto type is at offset 12 (0x0C) of Record 0 in PalmDOC / MOBI
    if len(rec0_data) >= 14:
        (crypto_type,) = struct.unpack_from(">H", rec0_data, 12)

    if has_mobi_magic and len(rec0_data) >= 40:
        # MOBI Header fields
        (mobi_header_len,) = struct.unpack_from(">I", rec0_data, 20)
        (version,) = struct.unpack_from(">I", rec0_data, 36)

        # Title offset and length from MOBI header (0x54 relative to Record 0)
        if len(rec0_data) >= 0x5C:
            toff, tlen = struct.unpack_from(">II", rec0_data, 0x54)
            if toff + tlen <= len(rec0_data) and tlen > 0:
                try:
                    title_bytes = rec0_data[toff : toff + tlen]
                    parsed_title = title_bytes.decode("utf-8", errors="replace").strip()
                    if parsed_title:
                        title = parsed_title
                except Exception:
                    pass

    # Check DRM encryption
    if crypto_type != 0:
        return PrecheckResult(
            is_valid=True,
            is_drm=True,
            crypto_type=crypto_type,
            version=version,
            title=title,
            error_reason="DRM protected: book is encrypted and cannot be converted",
        )

    return PrecheckResult(
        is_valid=True,
        is_drm=False,
        crypto_type=0,
        version=version,
        title=title,
    )
