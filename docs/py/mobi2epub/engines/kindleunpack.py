"""KindleUnpack conversion backend using the pure-Python mobi package."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from mobi2epub.engines.base import BaseEngine, EngineResult
from mobi2epub.precheck import check_mobi_file
from mobi2epub.validate import validate_epub

MAX_BS4_HTML_BYTES = 5 * 1024 * 1024


def convert_mobi7_html_to_xhtml(html_path: Path, xhtml_path: Path) -> None:
    """Convert MOBI7 book.html into standards-compliant XHTML."""
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    xml_decl = '<?xml version="1.0" encoding="utf-8"?>\n'
    doc_type = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'

    # Fast regex path for huge (>5 MB) HTML files to avoid large DOM tree allocation in WASM
    if len(content) > MAX_BS4_HTML_BYTES:
        cleaned = re.sub(r"<guide\b[^>]*>.*?</guide>", "", content, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(
            r"<mbp:pagebreak\b[^>]*/?>(\s*</mbp:pagebreak>)?",
            '<div class="mbp_pagebreak" style="page-break-after: always;"></div>',
            cleaned,
            flags=re.IGNORECASE,
        )
        if 'xmlns="http://www.w3.org/1999/xhtml"' not in cleaned[:1024]:
            cleaned = re.sub(
                r"<html\b",
                '<html xmlns="http://www.w3.org/1999/xhtml"',
                cleaned,
                count=1,
                flags=re.IGNORECASE,
            )
        with open(xhtml_path, "w", encoding="utf-8") as f:
            f.write(xml_decl + doc_type + cleaned)
        return

    soup = BeautifulSoup(content, "html.parser")

    # Remove proprietary tags inside head
    for tag in soup.find_all("guide"):
        tag.decompose()

    # Replace mbp:pagebreak with standard page-break div
    for tag in soup.find_all("mbp:pagebreak"):
        div = soup.new_tag("div", attrs={"class": "mbp_pagebreak", "style": "page-break-after: always;"})
        tag.replace_with(div)

    # Ensure html tag has standard XHTML namespace
    if soup.html:
        soup.html["xmlns"] = "http://www.w3.org/1999/xhtml"
        if "xml:lang" not in soup.html.attrs and "lang" in soup.html.attrs:
            soup.html["xml:lang"] = soup.html["lang"]

    xhtml_content = xml_decl + doc_type + soup.decode(formatter="minimal")

    with open(xhtml_path, "w", encoding="utf-8") as f:
        f.write(xhtml_content)


def package_mobi7_as_epub(mobi7_dir: Path, out_epub_path: Path) -> None:
    """Build a compliant EPUB from an unpacked mobi7 folder."""
    html_path = mobi7_dir / "book.html"
    xhtml_path = mobi7_dir / "book.xhtml"
    opf_path = mobi7_dir / "content.opf"
    ncx_path = mobi7_dir / "toc.ncx"
    images_dir = mobi7_dir / "Images"

    if html_path.exists():
        convert_mobi7_html_to_xhtml(html_path, xhtml_path)
        if xhtml_path.exists():
            try:
                html_path.unlink()
            except OSError:
                pass

    # Read and adjust OPF to reference book.xhtml and correct media types
    if opf_path.exists():
        with open(opf_path, "r", encoding="utf-8", errors="replace") as f:
            opf_text = f.read()

        # Update book.html to book.xhtml and media-type
        opf_text = (
            opf_text.replace('href="book.html"', 'href="book.xhtml"')
            .replace("href='book.html'", "href='book.xhtml'")
            .replace("book.html#", "book.xhtml#")
            .replace('media-type="text/html"', 'media-type="application/xhtml+xml"')
        )

        with open(opf_path, "w", encoding="utf-8") as f:
            f.write(opf_text)

    # Normalize toc.ncx links to book.xhtml during initial packaging to avoid re-packing later
    if ncx_path.exists() and xhtml_path.exists():
        with open(ncx_path, "r", encoding="utf-8", errors="replace") as f:
            ncx_text = f.read()
        if "book.html" in ncx_text:
            ncx_text = (
                ncx_text.replace('src="book.html"', 'src="book.xhtml"')
                .replace("src='book.html'", "src='book.xhtml'")
                .replace("book.html#", "book.xhtml#")
            )
            with open(ncx_path, "w", encoding="utf-8") as f:
                f.write(ncx_text)

    # Write container.xml
    container_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )

    with zipfile.ZipFile(out_epub_path, "w") as zf:
        # 1. mimetype MUST be first and stored uncompressed
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zinfo.external_attr = 0o644 << 16
        zf.writestr(zinfo, b"application/epub+zip")

        # 2. META-INF/container.xml
        zf.writestr("META-INF/container.xml", container_xml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)

        # 3. OPF file
        if opf_path.exists():
            zf.write(opf_path, "content.opf", compress_type=zipfile.ZIP_DEFLATED)

        # 4. NCX file
        if ncx_path.exists():
            zf.write(ncx_path, "toc.ncx", compress_type=zipfile.ZIP_DEFLATED)

        # 5. XHTML file
        if xhtml_path.exists():
            zf.write(xhtml_path, "book.xhtml", compress_type=zipfile.ZIP_DEFLATED)
            try:
                xhtml_path.unlink()
            except OSError:
                pass
        elif html_path.exists():
            zf.write(html_path, "book.html", compress_type=zipfile.ZIP_DEFLATED)
            try:
                html_path.unlink()
            except OSError:
                pass

        # 6. Images (unlink each unpacked image after adding to ZIP to minimize peak MEMFS usage)
        if images_dir.is_dir():
            for img_file in sorted(images_dir.iterdir()):
                if img_file.is_file():
                    zf.write(img_file, f"Images/{img_file.name}", compress_type=zipfile.ZIP_DEFLATED)
                    try:
                        img_file.unlink()
                    except OSError:
                        pass


class KindleUnpackEngine(BaseEngine):
    """Conversion engine using KindleUnpack (mobi package)."""

    @property
    def name(self) -> str:
        return "kindleunpack"

    def is_available(self) -> bool:
        try:
            import mobi
            return True
        except ImportError:
            return False

    def convert(self, src: Path, dst: Path) -> EngineResult:
        src = src.resolve()
        dst = dst.resolve()

        # Step 1: Pre-check header and DRM
        precheck = check_mobi_file(src)
        if not precheck.is_valid:
            return EngineResult(
                success=False,
                src_path=src,
                dst_path=dst,
                error_type="corrupt",
                error_message=precheck.error_reason or "Corrupt or invalid MOBI file",
                title=precheck.title,
            )

        if precheck.is_drm:
            return EngineResult(
                success=False,
                src_path=src,
                dst_path=dst,
                error_type="drm",
                error_message="DRM protected: book is encrypted and cannot be converted",
                title=precheck.title,
            )

        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Temporary file for atomic output
        temp_fd, temp_dst = tempfile.mkstemp(suffix=".epub", dir=dst.parent)
        os.close(temp_fd)
        temp_dst_path = Path(temp_dst)

        temp_dir_to_clean: Optional[str] = None
        try:
            import mobi

            # Extract MOBI
            try:
                temp_dir_to_clean, extracted_path = mobi.extract(str(src))
            except Exception as e:
                err_msg = str(e)
                if "DRM" in err_msg or "encrypted" in err_msg.lower():
                    return EngineResult(
                        success=False,
                        src_path=src,
                        dst_path=dst,
                        error_type="drm",
                        error_message="DRM protected: book is encrypted and cannot be converted",
                    )
                return EngineResult(
                    success=False,
                    src_path=src,
                    dst_path=dst,
                    error_type="unpack_error",
                    error_message=f"Failed to extract MOBI: {err_msg}",
                )

            extracted = Path(extracted_path)
            if extracted.suffix.lower() == ".epub":
                # KF8 produced a ready EPUB file — move instead of copying to avoid doubling peak disk/MEMFS usage
                shutil.move(str(extracted), str(temp_dst_path))
            elif extracted.suffix.lower() in (".html", ".htm") or (Path(temp_dir_to_clean) / "mobi7").is_dir():
                # MOBI7 unpack
                mobi7_dir = Path(temp_dir_to_clean) / "mobi7"
                if not mobi7_dir.is_dir():
                    mobi7_dir = extracted.parent
                package_mobi7_as_epub(mobi7_dir, temp_dst_path)
            else:
                return EngineResult(
                    success=False,
                    src_path=src,
                    dst_path=dst,
                    error_type="unsupported_format",
                    error_message=f"Unsupported unpack output format: {extracted.name}",
                )

            # Free unpacked temp_dir_to_clean immediately before validation
            if temp_dir_to_clean and os.path.exists(temp_dir_to_clean):
                shutil.rmtree(temp_dir_to_clean, ignore_errors=True)
                temp_dir_to_clean = None

            # Validate generated EPUB
            val = validate_epub(temp_dst_path)
            if not val.is_valid:
                return EngineResult(
                    success=False,
                    src_path=src,
                    dst_path=dst,
                    error_type="validation_error",
                    error_message=f"Output EPUB validation failed: {val.error_summary}",
                    title=val.title or precheck.title,
                )

            # Atomic replace
            temp_dst_path.replace(dst)

            return EngineResult(
                success=True,
                src_path=src,
                dst_path=dst,
                title=val.title or precheck.title,
            )

        except Exception as e:
            return EngineResult(
                success=False,
                src_path=src,
                dst_path=dst,
                error_type="conversion_error",
                error_message=str(e),
                title=precheck.title,
            )
        finally:
            if temp_dst_path.exists():
                try:
                    temp_dst_path.unlink()
                except OSError:
                    pass
            if temp_dir_to_clean and os.path.exists(temp_dir_to_clean):
                try:
                    shutil.rmtree(temp_dir_to_clean, ignore_errors=True)
                except OSError:
                    pass
