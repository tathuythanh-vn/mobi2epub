"""EPUB post-processing, inspection, preview, metadata/TOC editing, CSS injection, and chapter splitting."""

from __future__ import annotations

import base64
import mimetypes
import os
import posixpath
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from mobi2epub.validate import validate_epub

SUPPORTED_MOBI_EXTENSIONS = (".mobi", ".prc", ".azw3", ".azw")

# Memory bounds for Pyodide 32-bit WASM heap safety
MAX_COVER_IMAGE_BYTES = 5 * 1024 * 1024                # 5 MB max cover thumbnail to inline as Base64
MAX_PREVIEW_SINGLE_IMAGE_BYTES = int(1.5 * 1024 * 1024)  # 1.5 MB max per single inlined image in preview
MAX_PREVIEW_TOTAL_IMAGE_BYTES = 8 * 1024 * 1024        # 8 MB max cumulative inlined image bytes across preview
MAX_PREVIEW_HTML_CHARS = 12 * 1024 * 1024              # 12 MB max total HTML characters across preview
MAX_SPLIT_XHTML_BYTES = 5 * 1024 * 1024               # 5 MB max XHTML size for DOM chapter splitting

CSS_PRESETS: Dict[str, str] = {
    "serif": """/* mobi2epub custom-theme: serif */
body, p, div, li, blockquote {
  font-family: Georgia, "Palatino Linotype", Bookerly, "Times New Roman", serif !important;
  line-height: 1.6 !important;
  text-align: justify;
}
body {
  margin: 4% 6% !important;
}
h1, h2, h3, h4, h5, h6 {
  font-family: Georgia, "Palatino Linotype", Bookerly, serif !important;
  line-height: 1.3 !important;
  text-align: center;
  margin-top: 1.2em;
  margin-bottom: 0.6em;
}
p {
  margin-top: 0;
  margin-bottom: 0.45em;
  text-indent: 1.2em;
}
img, svg {
  max-width: 100% !important;
  height: auto !important;
}
""",
    "sans": """/* mobi2epub custom-theme: sans */
body, p, div, li, blockquote {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
  line-height: 1.55 !important;
  text-align: left;
}
body {
  margin: 4% 6% !important;
}
h1, h2, h3, h4, h5, h6 {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif !important;
  line-height: 1.25 !important;
  margin-top: 1.2em;
  margin-bottom: 0.5em;
}
p {
  margin-top: 0;
  margin-bottom: 0.75em;
  text-indent: 0;
}
img, svg {
  max-width: 100% !important;
  height: auto !important;
}
""",
    "dyslexia": """/* mobi2epub custom-theme: dyslexia */
body, p, div, li, blockquote {
  font-family: "OpenDyslexic", "Comic Sans MS", Verdana, Tahoma, Arial, sans-serif !important;
  line-height: 1.8 !important;
  letter-spacing: 0.06em !important;
  word-spacing: 0.16em !important;
  text-align: left !important;
}
body {
  margin: 5% 7% !important;
}
h1, h2, h3, h4, h5, h6 {
  font-family: "OpenDyslexic", Verdana, Tahoma, sans-serif !important;
  line-height: 1.4 !important;
  letter-spacing: 0.05em !important;
  text-align: left !important;
}
p {
  margin-top: 0;
  margin-bottom: 1em !important;
  text-indent: 0 !important;
}
img, svg {
  max-width: 100% !important;
  height: auto !important;
}
""",
}


def _local_tag(elem: ET.Element) -> str:
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _guess_image_mime(filename: str, fallback: str = "image/jpeg") -> str:
    lower = (filename or "").lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".svg"):
        return "image/svg+xml"
    guessed, _ = mimetypes.guess_type(lower)
    return guessed or fallback


def _resolve_zip_path(base_dir: str, href: str) -> str:
    if not href:
        return ""
    clean_href = href.split("#")[0].split("?")[0].replace("\\", "/")
    if base_dir:
        combined = f"{base_dir.rstrip('/')}/{clean_href}"
    else:
        combined = clean_href
    norm = posixpath.normpath(combined)
    return norm.lstrip("/")


def _find_opf_path(zf: zipfile.ZipFile) -> Optional[str]:
    names = zf.namelist()
    if "META-INF/container.xml" in names:
        try:
            c_root = ET.fromstring(zf.read("META-INF/container.xml"))
            for elem in c_root.iter():
                if _local_tag(elem).lower() == "rootfile":
                    fp = elem.attrib.get("full-path", "").replace("\\", "/")
                    if fp in names:
                        return fp
        except Exception:
            pass
    for name in names:
        if name.lower().endswith(".opf"):
            return name
    return None


def _repack_epub_dir(src_dir: Path, dst_epub: Path) -> None:
    """Write directory contents into an EPUB archive with uncompressed mimetype first."""
    all_files: List[Tuple[Path, str]] = []
    for root, _, files in os.walk(src_dir):
        for fname in files:
            full = Path(root) / fname
            rel = full.relative_to(src_dir).as_posix()
            all_files.append((full, rel))

    all_files.sort(key=lambda item: (0 if item[1] == "mimetype" else 1, item[1]))

    with zipfile.ZipFile(dst_epub, "w") as zf:
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zinfo.external_attr = 0o644 << 16
        mimetype_bytes = b"application/epub+zip"
        mimetype_file = src_dir / "mimetype"
        if mimetype_file.exists():
            raw = mimetype_file.read_bytes().strip()
            if raw:
                mimetype_bytes = raw
        zf.writestr(zinfo, mimetype_bytes)

        for full_path, arc_name in all_files:
            if arc_name == "mimetype":
                continue
            zf.write(full_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)


def _update_epub_archive(
    epub_path: Path,
    replacements: Dict[str, bytes],
    deleted: Optional[set[str]] = None,
) -> None:
    """Update specific entries in an EPUB archive by streaming untouched entries in 64 KB chunks.

    Never unpacks all ZIP entries into memory or onto disk (`temp_dir`), keeping Python RAM
    and Pyodide MEMFS overhead under a few hundred KB even on 100+ MB image-heavy EPUBs.
    """
    deleted_set = set(deleted or ())
    fd, tmp_name = tempfile.mkstemp(suffix=".epub", dir=epub_path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        with zipfile.ZipFile(epub_path, "r") as src_zf, zipfile.ZipFile(tmp_path, "w") as dst_zf:
            mimetype_bytes = replacements.get("mimetype")
            if mimetype_bytes is None:
                if "mimetype" in src_zf.namelist():
                    raw_mime = src_zf.read("mimetype").strip()
                    mimetype_bytes = raw_mime or b"application/epub+zip"
                else:
                    mimetype_bytes = b"application/epub+zip"

            zinfo = zipfile.ZipInfo("mimetype")
            zinfo.compress_type = zipfile.ZIP_STORED
            zinfo.external_attr = 0o644 << 16
            dst_zf.writestr(zinfo, mimetype_bytes)

            written: set[str] = {"mimetype"}

            for info in src_zf.infolist():
                arc = info.filename
                if arc in written or arc in deleted_set or info.is_dir():
                    continue
                if arc in replacements:
                    dst_zf.writestr(arc, replacements[arc], compress_type=zipfile.ZIP_DEFLATED)
                    written.add(arc)
                else:
                    out_info = zipfile.ZipInfo(arc, date_time=info.date_time)
                    out_info.compress_type = info.compress_type
                    out_info.external_attr = info.external_attr
                    with src_zf.open(info, "r") as src_f, dst_zf.open(out_info, "w") as dst_f:
                        shutil.copyfileobj(src_f, dst_f, length=65536)
                    written.add(arc)

            for arc in sorted(replacements.keys()):
                if arc in written or arc in deleted_set:
                    continue
                dst_zf.writestr(arc, replacements[arc], compress_type=zipfile.ZIP_DEFLATED)
                written.add(arc)

        tmp_path.replace(epub_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _extract_toc_from_zf(
    zf: zipfile.ZipFile,
    names: Optional[set[str]] = None,
    opf_path: Optional[str] = None,
    opf_root: Optional[ET.Element] = None,
) -> List[Dict[str, str]]:
    """Extract Table of Contents entries from an already-open ZipFile without reading image entries."""
    toc_entries: List[Dict[str, str]] = []
    if names is None:
        names = set(zf.namelist())
    if opf_path is None:
        opf_path = _find_opf_path(zf)
    opf_dir = posixpath.dirname(opf_path) if opf_path else ""

    ncx_zip_path: Optional[str] = None
    nav_zip_path: Optional[str] = None

    if opf_root is None and opf_path and opf_path in names:
        try:
            opf_root = ET.fromstring(zf.read(opf_path))
        except Exception:
            opf_root = None

    if opf_root is not None:
        for elem in opf_root.iter():
            if _local_tag(elem).lower() == "item":
                href = elem.attrib.get("href", "")
                mtype = elem.attrib.get("media-type", "").lower()
                props = elem.attrib.get("properties", "").lower()
                resolved = _resolve_zip_path(opf_dir, href)
                if mtype == "application/x-dtbncx+xml" or resolved.lower().endswith(".ncx"):
                    if resolved in names:
                        ncx_zip_path = resolved
                if "nav" in props.split() or resolved.lower().endswith("nav.xhtml"):
                    if resolved in names:
                        nav_zip_path = resolved

    if not ncx_zip_path:
        for n in zf.namelist():
            if n.lower().endswith(".ncx"):
                ncx_zip_path = n
                break

    if ncx_zip_path and ncx_zip_path in names:
        try:
            ncx_data = zf.read(ncx_zip_path)
            ncx_root = ET.fromstring(ncx_data)
            idx = 1
            for elem in ncx_root.iter():
                if _local_tag(elem).lower() == "navpoint":
                    nav_id = elem.attrib.get("id") or f"np_{idx}"
                    label_text = ""
                    content_src = ""
                    for child in elem:
                        ctag = _local_tag(child).lower()
                        if ctag == "navlabel":
                            for sub in child.iter():
                                if _local_tag(sub).lower() == "text" and sub.text:
                                    label_text = sub.text.strip()
                                    break
                        elif ctag == "content":
                            content_src = child.attrib.get("src", "").strip()
                    if label_text or content_src:
                        if content_src.startswith("book.html") and "book.xhtml" in names and "book.html" not in names:
                            content_src = "book.xhtml" + content_src[len("book.html"):]
                        label_clean = label_text or f"Section {idx}"
                        toc_entries.append({
                            "id": nav_id,
                            "label": label_clean,
                            "title": label_clean,
                            "href": content_src,
                        })
                        idx += 1
        except Exception:
            pass

    if not toc_entries and nav_zip_path and nav_zip_path in names:
        try:
            nav_html = zf.read(nav_zip_path).decode("utf-8", errors="replace")
            soup = BeautifulSoup(nav_html, "html.parser")
            nav_el = soup.find("nav") or soup
            for idx, a_tag in enumerate(nav_el.find_all("a", href=True), start=1):
                text = a_tag.get_text(" ", strip=True) or f"Section {idx}"
                href = a_tag["href"].strip()
                toc_entries.append({
                    "id": a_tag.get("id") or f"nav_{idx}",
                    "label": text,
                    "title": text,
                    "href": href,
                })
        except Exception:
            pass

    return toc_entries


def extract_epub_toc(epub_path: str | Path) -> List[Dict[str, str]]:
    """Extract Table of Contents entries [{ id, label, title, href }] from toc.ncx or nav.xhtml."""
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return []

    with zipfile.ZipFile(path, "r") as zf:
        return _extract_toc_from_zf(zf)


def inspect_epub_health(epub_path: str | Path) -> Dict[str, Any]:
    """Return structured EPUB health report (Feature #7) using only XML headers and ZipInfo metadata."""
    path = Path(epub_path)
    val = validate_epub(path)

    version = "2.0"
    xhtml_bytes = 0
    image_count = 0
    font_count = 0
    toc_count = 0

    mimetype_ok = False
    container_ok = False
    opf_ok = False
    spine_ok = False

    if path.exists() and zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path, "r") as zf:
                file_list = zf.namelist()
                names = set(file_list)
                if file_list and file_list[0] == "mimetype":
                    info = zf.getinfo("mimetype")
                    if info.compress_type == zipfile.ZIP_STORED and zf.read("mimetype").strip() == b"application/epub+zip":
                        mimetype_ok = True

                opf_path = _find_opf_path(zf)
                if "META-INF/container.xml" in names and opf_path and opf_path in names:
                    container_ok = True

                opf_root: Optional[ET.Element] = None
                if opf_path and opf_path in names:
                    try:
                        opf_root = ET.fromstring(zf.read(opf_path))
                        ver = opf_root.attrib.get("version", "").strip()
                        if ver:
                            version = ver
                        has_meta = any(_local_tag(c).lower() == "metadata" for c in opf_root)
                        has_manifest = any(_local_tag(c).lower() == "manifest" for c in opf_root)
                        has_spine = any(_local_tag(c).lower() == "spine" for c in opf_root)
                        opf_ok = bool(has_meta and has_manifest and has_spine)
                    except Exception:
                        opf_ok = False

                spine_ok = opf_ok and val.spine_items_count > 0 and not any(
                    "Spine" in err or "manifest" in err for err in val.errors
                )

                for info in zf.infolist():
                    lower = info.filename.lower()
                    if lower.endswith((".xhtml", ".html", ".htm")):
                        xhtml_bytes += info.file_size
                    elif lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
                        image_count += 1
                    elif lower.endswith((".ttf", ".otf", ".woff", ".woff2")):
                        font_count += 1

                toc_entries = _extract_toc_from_zf(zf, names=names, opf_path=opf_path, opf_root=opf_root)
                toc_count = len(toc_entries)
        except Exception:
            pass

    return {
        "version": version,
        "isValid": val.is_valid,
        "spineCount": val.spine_items_count,
        "xhtmlBytes": xhtml_bytes,
        "imageCount": image_count,
        "fontCount": font_count,
        "tocCount": toc_count,
        "checks": {
            "mimetypeUncompressed": mimetype_ok,
            "containerXmlValid": container_ok,
            "opfValid": opf_ok,
            "spineTargetsExist": spine_ok,
        },
        "errors": list(val.errors),
        "warnings": list(val.warnings),
    }


def _extract_metadata_and_cover_from_zf(
    zf: zipfile.ZipFile,
    epub_size: int = 0,
    names: Optional[set[str]] = None,
    opf_path: Optional[str] = None,
    opf_root: Optional[ET.Element] = None,
    max_cover_bytes: int = MAX_COVER_IMAGE_BYTES,
) -> Dict[str, Any]:
    """Extract metadata and bounded (<5 MB) cover image from an already-open ZipFile."""
    result: Dict[str, Any] = {
        "title": None,
        "author": "",
        "language": "en",
        "publisher": "",
        "description": "",
        "coverDataUrl": None,
        "coverHref": None,
        "coverMime": None,
        "epubSize": epub_size,
    }
    if names is None:
        names = set(zf.namelist())
    if opf_path is None:
        opf_path = _find_opf_path(zf)
    if not opf_path or opf_path not in names:
        return result

    opf_dir = posixpath.dirname(opf_path)
    if opf_root is None:
        try:
            opf_root = ET.fromstring(zf.read(opf_path))
        except Exception:
            return result

    metadata_el = None
    manifest_el = None
    for child in opf_root:
        tag = _local_tag(child).lower()
        if tag == "metadata":
            metadata_el = child
        elif tag == "manifest":
            manifest_el = child

    cover_meta_id: Optional[str] = None
    creators: List[str] = []

    if metadata_el is not None:
        for elem in metadata_el:
            ltag = _local_tag(elem).lower()
            text = (elem.text or "").strip()
            if ltag == "title" and text and not result["title"]:
                result["title"] = text
            elif ltag == "creator" and text:
                creators.append(text)
            elif ltag == "language" and text:
                result["language"] = text
            elif ltag == "publisher" and text and not result["publisher"]:
                result["publisher"] = text
            elif ltag == "description" and text and not result["description"]:
                result["description"] = text
            elif ltag == "meta":
                if elem.attrib.get("name", "").lower() == "cover":
                    cover_meta_id = elem.attrib.get("content", "").strip()

    if creators:
        result["author"] = ", ".join(creators)

    manifest_by_id: Dict[str, Tuple[str, str, str]] = {}
    if manifest_el is not None:
        for item in manifest_el:
            if _local_tag(item).lower() == "item":
                iid = item.attrib.get("id", "")
                href = item.attrib.get("href", "")
                mtype = item.attrib.get("media-type", "")
                props = item.attrib.get("properties", "")
                if iid and href:
                    manifest_by_id[iid] = (href, mtype, props)

    chosen_zip_path: Optional[str] = None
    chosen_mime: Optional[str] = None

    # 1. Check <meta name="cover" content="..."/>
    if cover_meta_id and cover_meta_id in manifest_by_id:
        href, mtype, _ = manifest_by_id[cover_meta_id]
        candidate = _resolve_zip_path(opf_dir, href)
        if candidate in names:
            chosen_zip_path = candidate
            chosen_mime = mtype or _guess_image_mime(candidate)

    # 2. Check properties="cover-image" or id with "cover"
    if not chosen_zip_path:
        for iid, (href, mtype, props) in manifest_by_id.items():
            if "cover-image" in props.split() or ("cover" in iid.lower() and mtype.startswith("image/")):
                candidate = _resolve_zip_path(opf_dir, href)
                if candidate in names:
                    chosen_zip_path = candidate
                    chosen_mime = mtype or _guess_image_mime(candidate)
                    break

    # 3. Check any image file in archive with "cover" in its name, or fallback to first image
    if not chosen_zip_path:
        image_files = [
            n for n in zf.namelist()
            if n.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
        ]
        for img_name in image_files:
            if "cover" in posixpath.basename(img_name).lower():
                chosen_zip_path = img_name
                chosen_mime = _guess_image_mime(img_name)
                break
        if not chosen_zip_path and image_files:
            chosen_zip_path = image_files[0]
            chosen_mime = _guess_image_mime(chosen_zip_path)

    if chosen_zip_path and chosen_zip_path in names:
        try:
            info = zf.getinfo(chosen_zip_path)
            mime = chosen_mime or _guess_image_mime(chosen_zip_path)
            result["coverHref"] = chosen_zip_path
            result["coverMime"] = mime
            if info.file_size <= max_cover_bytes:
                raw_bytes = zf.read(chosen_zip_path)
                b64 = base64.b64encode(raw_bytes).decode("ascii")
                result["coverDataUrl"] = f"data:{mime};base64,{b64}"
        except Exception:
            pass

    return result


def extract_epub_metadata_and_cover(
    epub_path: str | Path,
    max_cover_bytes: int = MAX_COVER_IMAGE_BYTES,
) -> Dict[str, Any]:
    """Extract book metadata (title, author, language, publisher, description) and coverDataUrl (Feature #5)."""
    path = Path(epub_path)
    epub_size = path.stat().st_size if path.exists() else 0
    if not path.exists() or not zipfile.is_zipfile(path):
        return {
            "title": None,
            "author": "",
            "language": "en",
            "publisher": "",
            "description": "",
            "coverDataUrl": None,
            "coverHref": None,
            "coverMime": None,
            "epubSize": epub_size,
        }

    with zipfile.ZipFile(path, "r") as zf:
        return _extract_metadata_and_cover_from_zf(zf, epub_size=epub_size, max_cover_bytes=max_cover_bytes)


def _inline_images_and_styles(
    html_text: str,
    html_dir: str,
    zf: zipfile.ZipFile,
    names: set[str],
    image_cache: Dict[str, str],
    budget_state: Optional[Dict[str, Any]] = None,
    max_single_image_bytes: int = MAX_PREVIEW_SINGLE_IMAGE_BYTES,
    max_total_image_bytes: int = MAX_PREVIEW_TOTAL_IMAGE_BYTES,
) -> str:
    """Inline relative images as base64 data URLs (with strict byte caps) and CSS links as <style> tags."""
    if budget_state is None:
        budget_state = {"total_bytes": 0, "exhausted": False}

    soup = BeautifulSoup(html_text, "html.parser")

    for link in list(soup.find_all("link", href=True)):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        if any("stylesheet" in r.lower() for r in rel) or link["href"].lower().endswith(".css"):
            css_zip_path = _resolve_zip_path(html_dir, link["href"])
            if css_zip_path in names:
                try:
                    if zf.getinfo(css_zip_path).file_size <= 512 * 1024:
                        css_text = zf.read(css_zip_path).decode("utf-8", errors="replace")
                        style_tag = soup.new_tag("style")
                        style_tag.string = css_text
                        link.replace_with(style_tag)
                except Exception:
                    pass

    for img in soup.find_all("img", src=True):
        src = img["src"].strip()
        if src.startswith("data:") or src.startswith("http://") or src.startswith("https://"):
            continue
        img_zip_path = _resolve_zip_path(html_dir, src)
        if img_zip_path not in names:
            continue

        try:
            raw_size = zf.getinfo(img_zip_path).file_size
        except Exception:
            raw_size = 0

        estimated_b64_size = ((raw_size + 2) // 3) * 4
        if (
            budget_state.get("exhausted")
            or raw_size > max_single_image_bytes
            or (budget_state["total_bytes"] + estimated_b64_size > max_total_image_bytes)
        ):
            if budget_state["total_bytes"] + estimated_b64_size > max_total_image_bytes:
                budget_state["exhausted"] = True
            img["alt"] = img.get("alt") or f"[Image omitted in preview: {posixpath.basename(img_zip_path)}]"
            del img["src"]
            continue

        if img_zip_path not in image_cache:
            try:
                raw = zf.read(img_zip_path)
                mime = _guess_image_mime(img_zip_path)
                image_cache[img_zip_path] = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            except Exception:
                image_cache[img_zip_path] = ""

        data_url = image_cache.get(img_zip_path) or ""
        if data_url:
            img["src"] = data_url
            budget_state["total_bytes"] += len(data_url)
        else:
            del img["src"]

    return str(soup)


def _build_chapters_preview(
    zf_or_path: zipfile.ZipFile | str | Path,
    toc: Optional[List[Dict[str, str]]] = None,
    max_chapters: int = 30,
    max_total_image_bytes: int = MAX_PREVIEW_TOTAL_IMAGE_BYTES,
    max_single_image_bytes: int = MAX_PREVIEW_SINGLE_IMAGE_BYTES,
) -> List[Dict[str, Any]]:
    """Build bounded HTML chapter previews for the in-browser reader with strict Base64 image memory limits."""
    if isinstance(zf_or_path, (str, Path)):
        path = Path(zf_or_path)
        if not path.exists() or not zipfile.is_zipfile(path):
            return []
        with zipfile.ZipFile(path, "r") as zf:
            return _build_chapters_preview(
                zf,
                toc=toc,
                max_chapters=max_chapters,
                max_total_image_bytes=max_total_image_bytes,
                max_single_image_bytes=max_single_image_bytes,
            )

    zf = zf_or_path
    names = set(zf.namelist())
    opf_path = _find_opf_path(zf)
    if not opf_path or opf_path not in names:
        return []

    opf_dir = posixpath.dirname(opf_path)
    try:
        opf_root = ET.fromstring(zf.read(opf_path))
    except Exception:
        return []

    if toc is None:
        toc = _extract_toc_from_zf(zf, names=names, opf_path=opf_path, opf_root=opf_root)

    manifest_hrefs: Dict[str, str] = {}
    spine_idrefs: List[str] = []

    for child in opf_root:
        tag = _local_tag(child).lower()
        if tag == "manifest":
            for item in child:
                if _local_tag(item).lower() == "item":
                    iid = item.attrib.get("id", "")
                    href = item.attrib.get("href", "")
                    if iid and href:
                        manifest_hrefs[iid] = href
        elif tag == "spine":
            for itemref in child:
                if _local_tag(itemref).lower() == "itemref":
                    idref = itemref.attrib.get("idref", "")
                    if idref:
                        spine_idrefs.append(idref)

    toc_title_by_href: Dict[str, str] = {}
    toc_title_by_anchor: Dict[str, str] = {}
    for entry in toc:
        ehref = entry.get("href", "")
        elabel = entry.get("label") or entry.get("title") or ""
        if ehref and elabel:
            toc_title_by_href[ehref] = elabel
            base_h = ehref.split("#")[0]
            if base_h not in toc_title_by_href:
                toc_title_by_href[base_h] = elabel
            if "#" in ehref:
                anchor = ehref.split("#", 1)[1]
                if anchor and anchor not in toc_title_by_anchor:
                    toc_title_by_anchor[anchor] = elabel

    chapters: List[Dict[str, Any]] = []
    image_cache: Dict[str, str] = {}
    budget_state: Dict[str, Any] = {"total_bytes": 0, "exhausted": False}
    total_html_chars = 0

    # Special case: single-file MOBI6 EPUB with mbp_pagebreak sections
    if len(spine_idrefs) == 1:
        only_id = spine_idrefs[0]
        only_href = manifest_hrefs.get(only_id, "")
        zip_target = _resolve_zip_path(opf_dir, only_href)
        if zip_target in names:
            info = zf.getinfo(zip_target)
            if info.file_size <= MAX_SPLIT_XHTML_BYTES:
                raw_html = zf.read(zip_target).decode("utf-8", errors="replace")
            else:
                with zf.open(zip_target, "r") as fh:
                    raw_html = fh.read(MAX_SPLIT_XHTML_BYTES).decode("utf-8", errors="replace")

            html_dir = posixpath.dirname(zip_target)
            parts = re.split(
                r'<div[^>]*class=["\'][^"\']*mbp_pagebreak[^"\']*["\'][^>]*>\s*</div>',
                raw_html,
                flags=re.IGNORECASE,
            )
            if len(parts) > 1:
                head_match = re.search(r"(<head\b[^>]*>.*?</head>)", raw_html, flags=re.IGNORECASE | re.DOTALL)
                raw_head_html = head_match.group(1) if head_match else "<head><meta charset='utf-8'/></head>"
                inlined_head_html = _inline_images_and_styles(
                    raw_head_html,
                    html_dir,
                    zf,
                    names,
                    image_cache,
                    budget_state=budget_state,
                    max_single_image_bytes=max_single_image_bytes,
                    max_total_image_bytes=max_total_image_bytes,
                )
                for idx, segment in enumerate(parts[:max_chapters], start=1):
                    if total_html_chars >= MAX_PREVIEW_HTML_CHARS:
                        break
                    body_fragment = segment
                    if idx == 1:
                        b_match = re.search(r"<body\b[^>]*>(.*)", segment, flags=re.IGNORECASE | re.DOTALL)
                        if b_match:
                            body_fragment = b_match.group(1)
                    body_fragment = re.sub(r"</body>\s*</html>\s*$", "", body_fragment, flags=re.IGNORECASE)
                    frag_soup = BeautifulSoup(body_fragment, "html.parser")
                    text_preview = frag_soup.get_text(" ", strip=True)
                    if not text_preview and not frag_soup.find("img"):
                        continue
                    anchors = [
                        a.get("id") or a.get("name")
                        for a in frag_soup.find_all(["a", "div", "h1", "h2", "h3", "p"])
                        if a.get("id") or a.get("name")
                    ]
                    first_anchor = anchors[0] if anchors else ""
                    chap_title = ""
                    for anc in anchors:
                        if anc in toc_title_by_anchor:
                            chap_title = toc_title_by_anchor[anc]
                            break
                    if not chap_title:
                        heading = frag_soup.find(["h1", "h2", "h3"])
                        if heading and heading.get_text(strip=True):
                            chap_title = heading.get_text(" ", strip=True)
                        elif text_preview:
                            chap_title = text_preview[:60] + ("..." if len(text_preview) > 60 else "")
                        else:
                            chap_title = f"Section {len(chapters) + 1}"

                    inlined_fragment = _inline_images_and_styles(
                        body_fragment,
                        html_dir,
                        zf,
                        names,
                        image_cache,
                        budget_state=budget_state,
                        max_single_image_bytes=max_single_image_bytes,
                        max_total_image_bytes=max_total_image_bytes,
                    )
                    chap_href = f"{only_href}#{first_anchor}" if first_anchor else only_href
                    full_chap_html = f"<!DOCTYPE html><html>{inlined_head_html}<body>{inlined_fragment}</body></html>"
                    total_html_chars += len(full_chap_html)
                    chapters.append({
                        "id": f"ch_{len(chapters) + 1}",
                        "title": chap_title,
                        "label": chap_title,
                        "href": chap_href,
                        "html": full_chap_html,
                    })
                if chapters:
                    return chapters

    for idx, idref in enumerate(spine_idrefs[:max_chapters], start=1):
        if total_html_chars >= MAX_PREVIEW_HTML_CHARS:
            break
        href = manifest_hrefs.get(idref, "")
        if not href:
            continue
        zip_target = _resolve_zip_path(opf_dir, href)
        if zip_target not in names:
            continue
        info = zf.getinfo(zip_target)
        if info.file_size <= MAX_SPLIT_XHTML_BYTES:
            raw_html = zf.read(zip_target).decode("utf-8", errors="replace")
        else:
            with zf.open(zip_target, "r") as fh:
                raw_html = fh.read(MAX_SPLIT_XHTML_BYTES).decode("utf-8", errors="replace")

        html_dir = posixpath.dirname(zip_target)
        soup = BeautifulSoup(raw_html, "html.parser")
        chap_title = toc_title_by_href.get(href) or ""
        if not chap_title:
            for el in soup.find_all(id=True):
                if el["id"] in toc_title_by_anchor:
                    chap_title = toc_title_by_anchor[el["id"]]
                    break
        if not chap_title:
            h_tag = soup.find(["h1", "h2", "h3"])
            if h_tag and h_tag.get_text(strip=True):
                chap_title = h_tag.get_text(" ", strip=True)
        if not chap_title:
            body_el = soup.body or soup
            txt = body_el.get_text(" ", strip=True)
            chap_title = (txt[:60] + ("..." if len(txt) > 60 else "")) if txt else f"Chapter {idx}"

        inlined_html = _inline_images_and_styles(
            raw_html,
            html_dir,
            zf,
            names,
            image_cache,
            budget_state=budget_state,
            max_single_image_bytes=max_single_image_bytes,
            max_total_image_bytes=max_total_image_bytes,
        )
        total_html_chars += len(inlined_html)
        chapters.append({
            "id": idref or f"ch_{idx}",
            "title": chap_title,
            "label": chap_title,
            "href": href,
            "html": inlined_html,
        })

    return chapters


def extract_epub_preview(
    epub_path: str | Path,
    max_chapters: int = 30,
    max_total_image_bytes: int = MAX_PREVIEW_TOTAL_IMAGE_BYTES,
    max_single_image_bytes: int = MAX_PREVIEW_SINGLE_IMAGE_BYTES,
) -> Dict[str, Any]:
    """Extract spine chapters and TOC for in-browser EPUB reader preview (Feature #6) with memory bounds."""
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return {"chapters": [], "chaptersPreview": [], "toc": []}

    with zipfile.ZipFile(path, "r") as zf:
        toc = _extract_toc_from_zf(zf)
        chapters = _build_chapters_preview(
            zf,
            toc=toc,
            max_chapters=max_chapters,
            max_total_image_bytes=max_total_image_bytes,
            max_single_image_bytes=max_single_image_bytes,
        )
    return {
        "chapters": chapters,
        "chaptersPreview": chapters,
        "toc": toc,
    }


def read_epub_preview(
    epub_path: str | Path,
    max_chapters: int = 30,
    max_total_image_bytes: int = MAX_PREVIEW_TOTAL_IMAGE_BYTES,
    max_single_image_bytes: int = MAX_PREVIEW_SINGLE_IMAGE_BYTES,
) -> Dict[str, Any]:
    """On-demand reader preview and metadata/health report with strict Base64 image memory caps."""
    return build_full_epub_report(
        epub_path,
        include_preview=True,
        max_chapters=max_chapters,
        max_total_image_bytes=max_total_image_bytes,
        max_single_image_bytes=max_single_image_bytes,
    )


def _check_needs_split(epub_path: Path, max_xhtml_bytes: int = MAX_SPLIT_XHTML_BYTES) -> bool:
    """Return True only if epub_path has a single spine item < max_xhtml_bytes with >= 2 split segments."""
    if not epub_path.exists() or not zipfile.is_zipfile(epub_path):
        return False

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            names = set(zf.namelist())
            opf_rel = _find_opf_path(zf)
            if not opf_rel or opf_rel not in names:
                return False

            opf_dir_str = posixpath.dirname(opf_rel)
            opf_root = ET.fromstring(zf.read(opf_rel))

            manifest_items: Dict[str, str] = {}
            spine_idrefs: List[str] = []
            for child in opf_root:
                ltag = _local_tag(child).lower()
                if ltag == "manifest":
                    for item in child:
                        if _local_tag(item).lower() == "item":
                            iid = item.attrib.get("id", "")
                            href = item.attrib.get("href", "")
                            if iid and href:
                                manifest_items[iid] = href
                elif ltag == "spine":
                    for itemref in child:
                        if _local_tag(itemref).lower() == "itemref":
                            idref = itemref.attrib.get("idref", "")
                            if idref:
                                spine_idrefs.append(idref)

            if len(spine_idrefs) != 1:
                return False

            orig_item_id = spine_idrefs[0]
            orig_href = manifest_items.get(orig_item_id, "book.xhtml")
            xhtml_zip_path = _resolve_zip_path(opf_dir_str, orig_href)
            if xhtml_zip_path not in names:
                return False

            xhtml_info = zf.getinfo(xhtml_zip_path)
            if xhtml_info.file_size <= 0 or xhtml_info.file_size >= max_xhtml_bytes:
                return False

            full_html = zf.read(xhtml_zip_path).decode("utf-8", errors="replace")
            body_match = re.search(r"<body\b[^>]*>(.*)</body>", full_html, flags=re.IGNORECASE | re.DOTALL)
            if not body_match:
                return False
            body_inner = body_match.group(1)

            raw_segments = re.split(
                r'<div[^>]*class=["\'][^"\']*mbp_pagebreak[^"\']*["\'][^>]*>\s*</div>',
                body_inner,
                flags=re.IGNORECASE,
            )
            if len([s for s in raw_segments if s.strip()]) < 2:
                raw_segments = re.split(r"(?=<h[12]\b[^>]*>)", body_inner, flags=re.IGNORECASE)

            non_empty = [s for s in raw_segments if s and s.strip()]
            return len(non_empty) >= 2
    except Exception:
        return False


def split_epub_chapters(epub_path: str | Path, max_xhtml_bytes: int = MAX_SPLIT_XHTML_BYTES) -> bool:
    """Split a single-file MOBI6 EPUB (book.xhtml) into part001.xhtml, part002.xhtml, ... (Feature #12).

    Rewrites internal #filepos links across parts and updates content.opf and toc.ncx.
    Never unpacks image entries to disk and skips giant (>= 5 MB) XHTML files.
    Returns True if the EPUB was split into multiple parts, False otherwise.
    """
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return False

    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        opf_rel = _find_opf_path(zf)
        if not opf_rel or opf_rel not in names:
            return False

        opf_dir_str = posixpath.dirname(opf_rel)
        opf_text = zf.read(opf_rel).decode("utf-8", errors="replace")
        try:
            opf_root = ET.fromstring(opf_text)
        except Exception:
            return False

        manifest_items: Dict[str, Tuple[str, str]] = {}
        spine_idrefs: List[str] = []
        for child in opf_root:
            ltag = _local_tag(child).lower()
            if ltag == "manifest":
                for item in child:
                    if _local_tag(item).lower() == "item":
                        iid = item.attrib.get("id", "")
                        href = item.attrib.get("href", "")
                        mtype = item.attrib.get("media-type", "")
                        if iid and href:
                            manifest_items[iid] = (href, mtype)
            elif ltag == "spine":
                for itemref in child:
                    if _local_tag(itemref).lower() == "itemref":
                        idref = itemref.attrib.get("idref", "")
                        if idref:
                            spine_idrefs.append(idref)

        if len(spine_idrefs) != 1:
            return False

        orig_item_id = spine_idrefs[0]
        orig_href, _ = manifest_items.get(orig_item_id, ("book.xhtml", "application/xhtml+xml"))
        xhtml_zip_path = _resolve_zip_path(opf_dir_str, orig_href)
        if xhtml_zip_path not in names:
            return False

        xhtml_info = zf.getinfo(xhtml_zip_path)
        if xhtml_info.file_size <= 0 or xhtml_info.file_size >= max_xhtml_bytes:
            return False

        full_html = zf.read(xhtml_zip_path).decode("utf-8", errors="replace")
        ncx_zip_path = _resolve_zip_path(opf_dir_str, "toc.ncx")
        ncx_text = zf.read(ncx_zip_path).decode("utf-8", errors="replace") if ncx_zip_path in names else None

    head_match = re.search(r"(<head\b[^>]*>.*?</head>)", full_html, flags=re.IGNORECASE | re.DOTALL)
    head_html = head_match.group(1) if head_match else '<head><meta content="text/html; charset=utf-8" http-equiv="content-type"/></head>'

    body_match = re.search(r"<body\b[^>]*>(.*)</body>", full_html, flags=re.IGNORECASE | re.DOTALL)
    if not body_match:
        return False
    body_inner = body_match.group(1)

    # 1. Try splitting on <div class="mbp_pagebreak">
    raw_segments = re.split(
        r'<div[^>]*class=["\'][^"\']*mbp_pagebreak[^"\']*["\'][^>]*>\s*</div>',
        body_inner,
        flags=re.IGNORECASE,
    )

    # 2. Fallback to splitting on <h1>/<h2> if fewer than 2 pagebreak sections
    if len([s for s in raw_segments if s.strip()]) < 2:
        raw_segments = re.split(r"(?=<h[12]\b[^>]*>)", body_inner, flags=re.IGNORECASE)

    if len([s for s in raw_segments if s and s.strip()]) < 2:
        return False

    # Merge anchor-only segments into the following segment so anchors are never orphaned
    merged_segments: List[str] = []
    pending_prefix = ""
    for seg in raw_segments:
        if not seg or not seg.strip():
            continue
        combined = pending_prefix + seg
        soup_check = BeautifulSoup(combined, "html.parser")
        has_visible = bool(soup_check.get_text(strip=True) or soup_check.find(["img", "svg", "hr", "table"]))
        if not has_visible:
            pending_prefix = combined
        else:
            merged_segments.append(combined)
            pending_prefix = ""

    if pending_prefix:
        if merged_segments:
            merged_segments[-1] += pending_prefix
        else:
            merged_segments.append(pending_prefix)

    if len(merged_segments) < 2:
        return False

    # First pass: map every anchor ID -> partNNN.xhtml
    part_entries: List[Tuple[str, str, str]] = []
    anchor_to_part: Dict[str, str] = {}

    for idx, seg_html in enumerate(merged_segments, start=1):
        part_id = f"part{idx:03d}"
        part_name = f"{part_id}.xhtml"
        for match in re.finditer(r'\b(?:id|name)=["\']([^"\']+)["\']', seg_html, flags=re.IGNORECASE):
            anc_val = match.group(1).strip()
            if anc_val:
                anchor_to_part[anc_val] = part_name
        part_entries.append((part_id, part_name, seg_html))

    # Second pass: rewrite internal #filepos / #anchor links across parts one segment at a time
    xml_decl = '<?xml version="1.0" encoding="utf-8"?>\n'
    doc_type = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
    orig_base_names = {posixpath.basename(orig_href), "book.html", "book.xhtml"}
    replacements: Dict[str, bytes] = {}

    for part_id, part_name, seg_html in part_entries:
        wrapped = (
            f'<html xmlns="http://www.w3.org/1999/xhtml">{head_html}'
            f"<body>{seg_html}</body></html>"
        )
        psoup = BeautifulSoup(wrapped, "html.parser")
        for a_tag in psoup.find_all("a", href=True):
            href_val = a_tag["href"].strip()
            if href_val.startswith("#"):
                anc = href_val[1:]
                target_part = anchor_to_part.get(anc)
                if target_part and target_part != part_name:
                    a_tag["href"] = f"{target_part}#{anc}"
            elif "#" in href_val:
                base_part, anc = href_val.split("#", 1)
                if posixpath.basename(base_part) in orig_base_names:
                    target_part = anchor_to_part.get(anc, "part001.xhtml")
                    a_tag["href"] = f"#{anc}" if target_part == part_name else f"{target_part}#{anc}"
            elif posixpath.basename(href_val) in orig_base_names:
                a_tag["href"] = "part001.xhtml"

        part_zip_path = _resolve_zip_path(opf_dir_str, part_name)
        replacements[part_zip_path] = (xml_decl + doc_type + psoup.decode(formatter="minimal")).encode("utf-8")

    # Update content.opf (<manifest>, <spine>, <guide>)
    manifest_items_xml = "\n".join(
        f'<item id="{pid}" media-type="application/xhtml+xml" href="{pname}" />'
        for pid, pname, _ in part_entries
    )
    spine_items_xml = "\n".join(
        f'<itemref idref="{pid}"/>'
        for pid, _, _ in part_entries
    )

    opf_updated = re.sub(
        rf'<item\b[^>]*\bid=["\']{re.escape(orig_item_id)}["\'][^>]*/?>',
        manifest_items_xml,
        opf_text,
        count=1,
    )
    opf_updated = re.sub(
        rf'<itemref\b[^>]*\bidref=["\']{re.escape(orig_item_id)}["\'][^>]*/?>',
        spine_items_xml,
        opf_updated,
        count=1,
    )

    def _rewrite_book_ref(match: re.Match) -> str:
        prefix, _, anchor, suffix = match.group(1), match.group(2), match.group(3), match.group(4)
        if anchor:
            anc_clean = anchor.lstrip("#")
            target_part = anchor_to_part.get(anc_clean, "part001.xhtml")
            return f"{prefix}{target_part}#{anc_clean}{suffix}"
        return f"{prefix}part001.xhtml{suffix}"

    opf_updated = re.sub(
        r'(href=["\'])(book\.x?html)(#[^"\']*)?(["\'])',
        _rewrite_book_ref,
        opf_updated,
    )
    replacements[opf_rel] = opf_updated.encode("utf-8")

    if ncx_text is not None:
        ncx_updated = re.sub(
            r'(src=["\'])(book\.x?html)(#[^"\']*)?(["\'])',
            _rewrite_book_ref,
            ncx_text,
        )
        replacements[ncx_zip_path] = ncx_updated.encode("utf-8")

    _update_epub_archive(path, replacements=replacements, deleted={xhtml_zip_path})
    return True


def inject_custom_css(epub_path: str | Path, css_preset: str) -> bool:
    """Inject Styles/custom-theme.css for 'serif', 'sans', or 'dyslexia' preset into the EPUB (Feature #11)."""
    preset_key = (css_preset or "").strip().lower()
    if preset_key not in CSS_PRESETS:
        return False

    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return False

    css_content = CSS_PRESETS[preset_key]
    replacements: Dict[str, bytes] = {}

    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        opf_rel = _find_opf_path(zf)
        if not opf_rel or opf_rel not in names:
            return False

        opf_dir_str = posixpath.dirname(opf_rel)
        css_zip_path = _resolve_zip_path(opf_dir_str, "Styles/custom-theme.css")
        replacements[css_zip_path] = css_content.encode("utf-8")

        opf_text = zf.read(opf_rel).decode("utf-8", errors="replace")
        if 'id="custom_theme_css"' not in opf_text and "Styles/custom-theme.css" not in opf_text:
            opf_text = opf_text.replace(
                "</manifest>",
                '<item id="custom_theme_css" media-type="text/css" href="Styles/custom-theme.css" />\n</manifest>',
                1,
            )
            replacements[opf_rel] = opf_text.encode("utf-8")

        for arc in zf.namelist():
            if not arc.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            if opf_dir_str and not arc.startswith(f"{opf_dir_str}/"):
                continue
            arc_dir = posixpath.dirname(arc)
            rel_css = posixpath.relpath(css_zip_path, arc_dir or ".").replace("\\", "/")
            xhtml_text = zf.read(arc).decode("utf-8", errors="replace")
            if "custom-theme.css" in xhtml_text:
                continue
            link_tag = f'<link rel="stylesheet" type="text/css" href="{rel_css}"/>'
            if "</head>" in xhtml_text:
                xhtml_text = xhtml_text.replace("</head>", f"{link_tag}</head>", 1)
            elif "<body" in xhtml_text:
                xhtml_text = xhtml_text.replace("<body", f"<head>{link_tag}</head><body", 1)
            replacements[arc] = xhtml_text.encode("utf-8")

    _update_epub_archive(path, replacements=replacements)
    return True


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def update_epub_toc(epub_path: str | Path, toc_override: List[Dict[str, Any]]) -> bool:
    """Rewrite toc.ncx to match toc_override (Feature #8) without unpacking image entries."""
    if toc_override is None:
        return False

    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return False

    replacements: Dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        opf_rel = _find_opf_path(zf)
        if not opf_rel or opf_rel not in names:
            return False

        opf_dir_str = posixpath.dirname(opf_rel)
        ncx_zip_path = _resolve_zip_path(opf_dir_str, "toc.ncx")
        opf_text = zf.read(opf_rel).decode("utf-8", errors="replace")

        default_href = "book.xhtml"
        try:
            opf_root = ET.fromstring(opf_text)
            for elem in opf_root.iter():
                if _local_tag(elem).lower() == "item" and elem.attrib.get("media-type") == "application/xhtml+xml":
                    default_href = elem.attrib.get("href") or default_href
                    break
        except Exception:
            pass

        navpoints_xml: List[str] = []
        for idx, item in enumerate(toc_override, start=1):
            label = (item.get("title") or item.get("label") or f"Section {idx}").strip()
            href = (item.get("href") or default_href).strip()
            nav_id = (item.get("id") or f"np_{idx}").strip()
            navpoints_xml.append(
                f'    <navPoint id="{_xml_escape(nav_id)}" playOrder="{idx}">\n'
                f"      <navLabel><text>{_xml_escape(label)}</text></navLabel>\n"
                f'      <content src="{_xml_escape(href)}"/>\n'
                f"    </navPoint>"
            )

        navmap_block = "<navMap>\n" + "\n".join(navpoints_xml) + "\n  </navMap>"

        if ncx_zip_path in names:
            ncx_text = zf.read(ncx_zip_path).decode("utf-8", errors="replace")
            if re.search(r"<navMap\b[^>]*>.*?</navMap>", ncx_text, flags=re.DOTALL):
                ncx_text = re.sub(
                    r"<navMap\b[^>]*>.*?</navMap>",
                    lambda _: navmap_block,
                    ncx_text,
                    count=1,
                    flags=re.DOTALL,
                )
            else:
                ncx_text = ncx_text.replace("</ncx>", f"  {navmap_block}\n</ncx>", 1)
            replacements[ncx_zip_path] = ncx_text.encode("utf-8")
        else:
            ncx_content = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="en">\n'
                "  <head>\n"
                '    <meta content="mobi2epub" name="dtb:uid"/>\n'
                '    <meta content="1" name="dtb:depth"/>\n'
                "  </head>\n"
                "  <docTitle><text>Table of Contents</text></docTitle>\n"
                f"  {navmap_block}\n"
                "</ncx>\n"
            )
            replacements[ncx_zip_path] = ncx_content.encode("utf-8")
            if "toc.ncx" not in opf_text:
                opf_text = opf_text.replace(
                    "</manifest>",
                    '<item id="ncx" media-type="application/x-dtbncx+xml" href="toc.ncx" />\n</manifest>',
                    1,
                )
                replacements[opf_rel] = opf_text.encode("utf-8")

    _update_epub_archive(path, replacements=replacements)
    return True


def _set_or_insert_dc_tag(opf_text: str, dc_name: str, value: str) -> str:
    escaped = _xml_escape(value)
    pattern = rf"(<dc:{dc_name}\b[^>]*>).*?(</dc:{dc_name}>)"
    if re.search(pattern, opf_text, flags=re.IGNORECASE | re.DOTALL):
        return re.sub(
            pattern,
            lambda m: f"{m.group(1)}{escaped}{m.group(2)}",
            opf_text,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    new_tag = f"<dc:{dc_name}>{escaped}</dc:{dc_name}>\n"
    if "</metadata>" in opf_text:
        return opf_text.replace("</metadata>", f"{new_tag}</metadata>", 1)
    return opf_text


def update_epub_metadata_and_cover(
    epub_path: str | Path,
    metadata_override: Optional[Dict[str, Any]] = None,
    cover_override: Optional[Dict[str, Any]] = None,
    toc_override: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Update OPF metadata, replace/insert cover image, and optionally update TOC (Feature #9 & #8)."""
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return False

    changed = False
    replacements: Dict[str, bytes] = {}

    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        opf_rel = _find_opf_path(zf)
        if not opf_rel or opf_rel not in names:
            return False

        opf_dir_str = posixpath.dirname(opf_rel)
        opf_text = zf.read(opf_rel).decode("utf-8", errors="replace")
        ncx_zip_path = _resolve_zip_path(opf_dir_str, "toc.ncx")

        if metadata_override:
            field_map = {
                "title": "title",
                "author": "creator",
                "language": "language",
                "publisher": "publisher",
                "description": "description",
            }
            for key, dc_tag in field_map.items():
                val = metadata_override.get(key)
                if val is not None and str(val).strip() != "":
                    opf_text = _set_or_insert_dc_tag(opf_text, dc_tag, str(val).strip())
                    changed = True

            if metadata_override.get("title") and ncx_zip_path in names:
                new_title = str(metadata_override["title"]).strip()
                ncx_text = zf.read(ncx_zip_path).decode("utf-8", errors="replace")
                ncx_text = re.sub(
                    r"(<docTitle>\s*<text>).*?(</text>\s*</docTitle>)",
                    lambda m: f"{m.group(1)}{_xml_escape(new_title)}{m.group(2)}",
                    ncx_text,
                    count=1,
                    flags=re.DOTALL,
                )
                replacements[ncx_zip_path] = ncx_text.encode("utf-8")

        if cover_override:
            cover_bytes: Optional[bytes] = None
            cover_mime: str = "image/jpeg"

            if isinstance(cover_override, (bytes, bytearray)):
                cover_bytes = bytes(cover_override)
            elif isinstance(cover_override, str) and cover_override.startswith("data:"):
                if "," in cover_override:
                    header, b64_part = cover_override.split(",", 1)
                    if "image/png" in header:
                        cover_mime = "image/png"
                    elif "image/webp" in header:
                        cover_mime = "image/webp"
                    cover_bytes = base64.b64decode(b64_part)
            elif isinstance(cover_override, dict):
                cover_mime = cover_override.get("mime") or "image/jpeg"
                if cover_override.get("bytes") is not None or cover_override.get("data") is not None:
                    raw_b = cover_override.get("bytes") if cover_override.get("bytes") is not None else cover_override.get("data")
                    if isinstance(raw_b, (bytes, bytearray)):
                        cover_bytes = bytes(raw_b)
                    elif isinstance(raw_b, list):
                        cover_bytes = bytes(raw_b)
                elif cover_override.get("diskPath"):
                    dp = Path(cover_override["diskPath"])
                    if dp.exists():
                        cover_bytes = dp.read_bytes()
                elif cover_override.get("dataUrl") or cover_override.get("base64"):
                    durl = cover_override.get("dataUrl") or cover_override.get("base64") or ""
                    if "," in durl:
                        header, b64_part = durl.split(",", 1)
                        if "image/png" in header:
                            cover_mime = "image/png"
                        elif "image/webp" in header:
                            cover_mime = "image/webp"
                        cover_bytes = base64.b64decode(b64_part)
                    elif durl:
                        cover_bytes = base64.b64decode(durl)

            if cover_bytes:
                ext = ".png" if "png" in cover_mime.lower() else ".jpg"
                cover_rel_href = f"Images/custom_cover{ext}"
                cover_zip_path = _resolve_zip_path(opf_dir_str, cover_rel_href)
                replacements[cover_zip_path] = cover_bytes

                cover_id = "cover_img"
                meta_match = re.search(
                    r'<meta\b[^>]*name=["\']cover["\'][^>]*content=["\']([^"\']+)["\']',
                    opf_text,
                    flags=re.IGNORECASE,
                )
                if meta_match:
                    cover_id = meta_match.group(1)
                else:
                    opf_text = opf_text.replace(
                        "</metadata>",
                        f'<meta name="cover" content="{cover_id}" />\n</metadata>',
                        1,
                    )

                item_pattern = rf'<item\b[^>]*\bid=["\']{re.escape(cover_id)}["\'][^>]*/?>'
                new_item_tag = f'<item id="{cover_id}" media-type="{cover_mime}" href="{cover_rel_href}" />'
                if re.search(item_pattern, opf_text, flags=re.IGNORECASE):
                    opf_text = re.sub(item_pattern, new_item_tag, opf_text, count=1, flags=re.IGNORECASE)
                else:
                    opf_text = opf_text.replace("</manifest>", f"{new_item_tag}\n</manifest>", 1)

                changed = True

        if changed:
            replacements[opf_rel] = opf_text.encode("utf-8")

    if changed and replacements:
        _update_epub_archive(path, replacements=replacements)

    if toc_override is not None:
        update_epub_toc(path, toc_override)
        changed = True

    return changed


def list_epub_images(epub_path: str | Path) -> List[Dict[str, str]]:
    """List raster images inside an EPUB archive for Worker OffscreenCanvas optimization (Feature #13)."""
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return []
    images: List[Dict[str, str]] = []
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
                images.append({
                    "arcName": name,
                    "mime": _guess_image_mime(name),
                })
    return images


def replace_epub_files(epub_path: str | Path, replacements: Dict[str, bytes]) -> bool:
    """Replace specific files in an EPUB archive while preserving uncompressed mimetype first."""
    if not replacements:
        return False
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return False

    _update_epub_archive(path, replacements=replacements)
    return True


def extract_mobi_from_zip(zip_path: str | Path, out_dir: str | Path) -> List[Dict[str, Any]]:
    """Extract all .mobi, .prc, .azw3, .azw files from an input .zip archive (Feature #14)."""
    zpath = Path(zip_path)
    dest_root = Path(out_dir)
    dest_root.mkdir(parents=True, exist_ok=True)

    if not zpath.exists() or not zipfile.is_zipfile(zpath):
        return []

    extracted_files: List[Dict[str, Any]] = []
    with zipfile.ZipFile(zpath, "r") as zf:
        for idx, info in enumerate(zf.infolist()):
            if info.is_dir():
                continue
            rel_path = info.filename.replace("\\", "/").lstrip("/")
            if not rel_path or rel_path.startswith("__MACOSX/"):
                continue
            base_name = posixpath.basename(rel_path)
            if base_name.startswith("._"):
                continue
            if not base_name.lower().endswith(SUPPORTED_MOBI_EXTENSIONS):
                continue

            disk_path = dest_root / f"extracted_{idx}_{base_name}"
            with zf.open(info, "r") as src_f, open(disk_path, "wb") as dst_f:
                shutil.copyfileobj(src_f, dst_f, length=65536)
            extracted_files.append({
                "fileName": base_name,
                "relPath": rel_path,
                "diskPath": str(disk_path),
                "size": info.file_size,
            })

    extracted_files.sort(key=lambda item: item["relPath"].lower())
    return extracted_files


def normalize_epub_ncx_links(epub_path: str | Path) -> bool:
    """Normalize legacy book.html references in toc.ncx and content.opf to book.xhtml when appropriate."""
    path = Path(epub_path)
    if not path.exists() or not zipfile.is_zipfile(path):
        return False

    replacements: Dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        if "book.xhtml" not in names or "book.html" in names:
            return False
        for check_name in ("toc.ncx", "content.opf"):
            if check_name in names:
                txt = zf.read(check_name).decode("utf-8", errors="replace")
                if "book.html" in txt:
                    updated = (
                        txt.replace("book.html#", "book.xhtml#")
                        .replace('src="book.html"', 'src="book.xhtml"')
                        .replace('href="book.html"', 'href="book.xhtml"')
                    )
                    if updated != txt:
                        replacements[check_name] = updated.encode("utf-8")

    if not replacements:
        return False

    _update_epub_archive(path, replacements=replacements)
    return True


def build_full_epub_report(
    epub_path: str | Path,
    include_preview: bool = False,
    max_chapters: int = 30,
    max_total_image_bytes: int = MAX_PREVIEW_TOTAL_IMAGE_BYTES,
    max_single_image_bytes: int = MAX_PREVIEW_SINGLE_IMAGE_BYTES,
) -> Dict[str, Any]:
    """Assemble metadata, coverDataUrl, healthReport, toc, and (optionally) chaptersPreview for an EPUB.

    By default (`include_preview=False`), `chaptersPreview` is `[]` and only small XML files + a bounded
    cover image (< 5 MB) are read from the archive, avoiding `MemoryError` in `json.dumps` on large books.
    """
    path = Path(epub_path)
    meta = extract_epub_metadata_and_cover(path)
    health = inspect_epub_health(path)
    if include_preview:
        preview = extract_epub_preview(
            path,
            max_chapters=max_chapters,
            max_total_image_bytes=max_total_image_bytes,
            max_single_image_bytes=max_single_image_bytes,
        )
        toc = preview.get("toc") or []
        chapters = preview.get("chapters") or []
    else:
        toc = extract_epub_toc(path)
        chapters = []

    return {
        "title": meta.get("title"),
        "author": meta.get("author") or "",
        "language": meta.get("language") or "en",
        "publisher": meta.get("publisher") or "",
        "description": meta.get("description") or "",
        "coverDataUrl": meta.get("coverDataUrl"),
        "epubSize": path.stat().st_size if path.exists() else 0,
        "version": health.get("version") or "2.0",
        "spineCount": health.get("spineCount") or 0,
        "healthReport": health,
        "toc": toc,
        "chaptersPreview": chapters,
        "chapters": chapters,
    }


def process_epub_features(
    epub_path: str | Path,
    css_preset: Optional[str | Dict[str, Any]] = "original",
    auto_split_chapters: bool = False,
    metadata_override: Optional[Dict[str, Any]] = None,
    cover_override: Optional[Dict[str, Any]] = None,
    toc_override: Optional[List[Dict[str, Any]]] = None,
    include_preview: bool = False,
    options: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Apply requested EPUB feature modifications with a Zero-Rewrite Fast Path when no edits are needed.

    - Defaults to `include_preview=False` (`chaptersPreview: []`) so `convert_one` never inlines all book
      images into JSON.
    - When `not needs_modify` (`css_preset` in `("original", "default", "")`, no metadata/cover/TOC overrides,
      and `not needs_split`), does NOT rewrite the `.epub` ZIP on disk at all and reads only the small XML
      files + cover image (< 5 MB) from `zipfile.ZipFile(epub_path, "r")`.
    """
    path = Path(epub_path)

    if isinstance(css_preset, dict) and options is None:
        options = css_preset
        css_preset = "original"

    if isinstance(options, dict):
        if css_preset in (None, "original"):
            css_preset = options.get("cssPreset") or options.get("css_preset") or "original"
        if not auto_split_chapters:
            auto_split_chapters = bool(
                options.get("autoSplitChapters")
                if "autoSplitChapters" in options
                else options.get("auto_split_chapters", False)
            )
        if metadata_override is None:
            metadata_override = options.get("metadataOverride") or options.get("metadata_override")
        if cover_override is None:
            cover_override = (
                options.get("coverOverride")
                or options.get("cover_override")
                or options.get("coverFsInfo")
            )
        if toc_override is None:
            toc_override = options.get("tocOverride") if "tocOverride" in options else options.get("toc_override")
        if "include_preview" in options or "includePreview" in options:
            include_preview = bool(options.get("include_preview") or options.get("includePreview"))

    if "auto_split" in kwargs and not auto_split_chapters:
        auto_split_chapters = bool(kwargs["auto_split"])

    preset_clean = str(css_preset or "").strip().lower()
    needs_css = bool(preset_clean and preset_clean not in ("original", "default", "") and preset_clean in CSS_PRESETS)

    has_meta_override = bool(
        isinstance(metadata_override, dict)
        and any(v is not None and str(v).strip() != "" for v in metadata_override.values())
    )
    has_cover_override = False
    if isinstance(cover_override, (bytes, bytearray)) and len(cover_override) > 0:
        has_cover_override = True
    elif isinstance(cover_override, str) and cover_override.startswith("data:"):
        has_cover_override = True
    elif isinstance(cover_override, dict):
        has_cover_override = bool(
            cover_override.get("bytes")
            or cover_override.get("data")
            or cover_override.get("dataUrl")
            or cover_override.get("base64")
            or cover_override.get("diskPath")
        )

    has_toc_override = toc_override is not None
    needs_split = bool(auto_split_chapters) and _check_needs_split(path, max_xhtml_bytes=MAX_SPLIT_XHTML_BYTES)
    needs_modify = has_meta_override or has_cover_override or has_toc_override or needs_css or needs_split

    if needs_modify:
        if needs_split:
            split_epub_chapters(path, max_xhtml_bytes=MAX_SPLIT_XHTML_BYTES)
        if needs_css:
            inject_custom_css(path, preset_clean)
        if has_meta_override or has_cover_override or has_toc_override:
            update_epub_metadata_and_cover(
                path,
                metadata_override=metadata_override if has_meta_override else None,
                cover_override=cover_override if has_cover_override else None,
                toc_override=toc_override if has_toc_override else None,
            )

    return build_full_epub_report(path, include_preview=include_preview)
