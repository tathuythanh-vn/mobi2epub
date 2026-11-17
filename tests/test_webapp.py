"""Automated test suite for the static Web App (docs/), PWA assets, bundle.zip, and epub_tools."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures"


def _load_bundle_module(tmp_path: Path, module_rel_path: str, module_name: str) -> ModuleType:
    """Extract docs/py/bundle.zip into an isolated directory and load a module from it."""
    bundle_zip = DOCS_DIR / "py" / "bundle.zip"
    assert bundle_zip.exists(), "docs/py/bundle.zip must exist"

    extract_dir = tmp_path / "bundle_extracted"
    if not extract_dir.exists():
        with zipfile.ZipFile(bundle_zip, "r") as zf:
            zf.extractall(extract_dir)

    import mobi2epub

    bundle_pkg_dir = str(extract_dir / "mobi2epub")
    if bundle_pkg_dir not in mobi2epub.__path__:
        mobi2epub.__path__.insert(0, bundle_pkg_dir)

    target_file = extract_dir / module_rel_path
    assert target_file.exists(), f"{module_rel_path} missing in bundle.zip"

    spec = importlib.util.spec_from_file_location(module_name, target_file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bundle_zip_and_manifest_integrity():
    """Verify docs/py/bundle.zip and docs/py/manifest.json exist and contain all required modules."""
    bundle_path = DOCS_DIR / "py" / "bundle.zip"
    manifest_path = DOCS_DIR / "py" / "manifest.json"

    assert bundle_path.exists(), "docs/py/bundle.zip is missing"
    assert manifest_path.exists(), "docs/py/manifest.json is missing"
    assert zipfile.is_zipfile(bundle_path), "docs/py/bundle.zip is not a valid ZIP archive"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_files = manifest.get("files", [])
    assert len(manifest_files) >= 13

    required_modules = {
        "mobi2epub/__init__.py",
        "mobi2epub/precheck.py",
        "mobi2epub/validate.py",
        "mobi2epub/epub_tools.py",
        "mobi2epub/engines/__init__.py",
        "mobi2epub/engines/base.py",
        "mobi2epub/engines/kindleunpack.py",
    }
    assert required_modules.issubset(set(manifest_files))

    with zipfile.ZipFile(bundle_path, "r") as zf:
        assert zf.testzip() is None, "Corrupt entry found in docs/py/bundle.zip"
        zip_names = set(zf.namelist())
        for rel_file in manifest_files:
            assert rel_file in zip_names, f"{rel_file} listed in manifest.json but missing from bundle.zip"
            disk_copy = DOCS_DIR / "py" / rel_file
            assert disk_copy.exists(), f"docs/py/{rel_file} missing on disk"
            assert zf.read(rel_file) == disk_copy.read_bytes(), (
                f"docs/py/bundle.zip entry {rel_file} is out of sync with docs/py/{rel_file}"
            )


def test_pwa_manifest_and_icons():
    """Verify Feature #1: docs/manifest.webmanifest is valid JSON and all icons exist."""
    manifest_file = DOCS_DIR / "manifest.webmanifest"
    assert manifest_file.exists(), "docs/manifest.webmanifest is missing"

    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert data["name"] == "MobiToEpub Converter"
    assert data["short_name"] == "MobiToEpub"
    assert data["start_url"] == "./"
    assert data["scope"] == "./"
    assert data["display"] == "standalone"
    assert data["background_color"] == "#0f172a"
    assert data["theme_color"] == "#2e7d32"

    icons = data.get("icons", [])
    assert len(icons) >= 3
    srcs = {icon["src"] for icon in icons}
    assert "./favicon.ico" in srcs
    assert "./icon-192.png" in srcs
    assert "./icon-512.png" in srcs

    for icon in icons:
        rel_src = icon["src"].lstrip("./")
        icon_path = DOCS_DIR / rel_src
        assert icon_path.exists(), f"PWA icon {icon['src']} does not exist at {icon_path}"
        assert icon_path.stat().st_size > 100

    # Verify PNG magic header on generated icons
    for png_name in ("icon-192.png", "icon-512.png"):
        raw = (DOCS_DIR / png_name).read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{png_name} is not a valid PNG file"


def test_service_worker_shell_and_caching_rules():
    """Verify Feature #1: docs/sw.js caches the local app shell and Pyodide CDN assets."""
    sw_path = DOCS_DIR / "sw.js"
    assert sw_path.exists(), "docs/sw.js is missing"
    sw_text = sw_path.read_text(encoding="utf-8")

    required_shell_entries = [
        "./",
        "./index.html",
        "./styles.css",
        "./app.js",
        "./worker.js",
        "./manifest.webmanifest",
        "./favicon.ico",
        "./sample.mobi",
        "./py/bundle.zip",
        "./py/manifest.json",
    ]
    for entry in required_shell_entries:
        assert entry in sw_text, f"App shell asset {entry} missing from docs/sw.js"

    assert "cdn.jsdelivr.net" in sw_text
    assert "pyodide" in sw_text.lower()


def test_javascript_syntax_with_node_check():
    """Verify Feature #18: node --check passes on docs/app.js, docs/worker.js, and docs/sw.js."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js binary not found in PATH")

    for js_name in ("app.js", "worker.js", "sw.js"):
        js_path = DOCS_DIR / js_name
        assert js_path.exists(), f"docs/{js_name} does not exist"
        proc = subprocess.run(
            [node_bin, "--check", str(js_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"node --check failed for docs/{js_name}:\n{proc.stderr}"


def test_github_pages_relative_path_compliance():
    """Ensure docs/ files use relative paths ('./...') so hosting under /mobi2epub/ subpath works."""
    index_html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
    assert "./manifest.webmanifest" in index_html
    assert "./styles.css" in index_html
    assert "./app.js" in index_html

    # Disallow root-relative href="/..." or src="/..." in index.html
    bad_root_refs = re.findall(r'(?:href|src)=["\']/(?!/)[a-zA-Z0-9_.-]+', index_html)
    assert not bad_root_refs, f"Root-relative URLs found in docs/index.html: {bad_root_refs}"


def test_isolated_bundle_conversion_and_features(tmp_path: Path):
    """Test isolated conversion + Features #5, #6, #7, #8, #9, #11, #12, #14 using docs/py/bundle.zip."""
    epub_tools = _load_bundle_module(tmp_path, "mobi2epub/epub_tools.py", "mobi2epub.epub_tools")
    from mobi2epub.engines.kindleunpack import KindleUnpackEngine
    from mobi2epub.precheck import check_mobi_file
    from mobi2epub.validate import validate_epub

    # 1. Precheck on corrupt & DRM fixtures
    corrupt_res = check_mobi_file(FIXTURES_DIR / "corrupt.mobi")
    assert not corrupt_res.is_valid

    drm_res = check_mobi_file(FIXTURES_DIR / "drm_protected.mobi")
    assert drm_res.is_valid and drm_res.is_drm

    # 2. Convert sample_mobi6.mobi to EPUB
    sample_mobi = FIXTURES_DIR / "sample_mobi6.mobi"
    epub_path = tmp_path / "alice.epub"
    engine = KindleUnpackEngine()
    conv = engine.convert(sample_mobi, epub_path)
    assert conv.success and epub_path.exists()
    epub_tools.normalize_epub_ncx_links(epub_path)

    # 3. Feature #5: Metadata & Cover extraction
    meta = epub_tools.extract_epub_metadata_and_cover(epub_path)
    assert "Alice" in (meta["title"] or "")
    assert meta["epubSize"] > 0

    # 4. Feature #7: EPUB Structure & Health Report
    health = epub_tools.inspect_epub_health(epub_path)
    assert health["isValid"] is True
    assert health["spineCount"] >= 1
    assert health["xhtmlBytes"] > 0
    assert health["checks"]["mimetypeUncompressed"] is True
    assert health["checks"]["containerXmlValid"] is True
    assert health["checks"]["opfValid"] is True
    assert health["checks"]["spineTargetsExist"] is True

    # 5. Feature #6: Built-in Reader Preview extraction
    preview = epub_tools.extract_epub_preview(epub_path)
    assert len(preview["chapters"]) >= 1
    assert any("Alice" in ch.get("html", "") or "CHAPTER" in ch.get("html", "") for ch in preview["chapters"])

    # 6. Feature #8: TOC extraction & TOC override
    orig_toc = epub_tools.extract_epub_toc(epub_path)
    assert isinstance(orig_toc, list)
    custom_toc = [
        {"id": "np_1", "title": "Chapter I: Down the Rabbit-Hole", "href": "book.xhtml"},
        {"id": "np_2", "title": "Chapter II: The Pool of Tears", "href": "book.xhtml"},
    ]
    assert epub_tools.update_epub_toc(epub_path, custom_toc) is True
    updated_toc = epub_tools.extract_epub_toc(epub_path)
    assert len(updated_toc) == 2
    assert updated_toc[0]["title"] == "Chapter I: Down the Rabbit-Hole"
    assert updated_toc[1]["title"] == "Chapter II: The Pool of Tears"

    # 7. Feature #9: Metadata & Cover Override
    custom_cover_bytes = (DOCS_DIR / "icon-192.png").read_bytes()
    updated = epub_tools.update_epub_metadata_and_cover(
        epub_path,
        metadata_override={
            "title": "Alice in Wonderland (Edited)",
            "author": "Lewis Carroll",
            "language": "vi",
            "publisher": "Wonderland Press",
            "description": "Custom edition tested by pytest.",
        },
        cover_override={
            "bytes": custom_cover_bytes,
            "mime": "image/png",
        },
    )
    assert updated is True
    meta_after = epub_tools.extract_epub_metadata_and_cover(epub_path)
    assert meta_after["title"] == "Alice in Wonderland (Edited)"
    assert meta_after["author"] == "Lewis Carroll"
    assert meta_after["language"] == "vi"
    assert meta_after["publisher"] == "Wonderland Press"
    assert meta_after["description"] == "Custom edition tested by pytest."
    assert meta_after["coverDataUrl"] is not None
    assert meta_after["coverDataUrl"].startswith("data:image/png;base64,")
    assert validate_epub(epub_path).is_valid

    # 8. Feature #11: Custom CSS / Typography Injection
    for preset in ("serif", "sans", "dyslexia"):
        css_epub = tmp_path / f"alice_{preset}.epub"
        shutil.copyfile(epub_path, css_epub)
        assert epub_tools.inject_custom_css(css_epub, preset) is True
        with zipfile.ZipFile(css_epub, "r") as zf:
            names = set(zf.namelist())
            assert any(n.endswith("Styles/custom-theme.css") for n in names)
        assert validate_epub(css_epub).is_valid

    # 9. Feature #12: Auto-Split Large HTML Chapters
    split_epub = tmp_path / "alice_split.epub"
    engine.convert(sample_mobi, split_epub)
    epub_tools.normalize_epub_ncx_links(split_epub)
    # Inject a synthetic multi-section MOBI6 book.xhtml with mbp_pagebreak & cross-section #filepos link
    with zipfile.ZipFile(split_epub, "r") as zf:
        orig_xhtml = zf.read("book.xhtml").decode("utf-8", errors="replace")
    synthetic_xhtml = orig_xhtml.replace(
        "</body>",
        '<p><a href="#filepos999999">Jump to Bonus Chapter</a></p>'
        '<div class="mbp_pagebreak"></div>'
        '<h2 id="filepos999999">Bonus Chapter</h2><p>Second split part content.</p></body>',
    )
    epub_tools.replace_epub_files(split_epub, {"book.xhtml": synthetic_xhtml.encode("utf-8")})
    did_split = epub_tools.split_epub_chapters(split_epub)
    assert did_split is True
    split_health = epub_tools.inspect_epub_health(split_epub)
    assert split_health["isValid"] is True
    assert split_health["spineCount"] >= 2
    with zipfile.ZipFile(split_epub, "r") as zf:
        part_names = sorted(n for n in zf.namelist() if re.match(r"^part\d+\.xhtml$", n))
        assert len(part_names) >= 2
        penultimate_html = zf.read(part_names[-2]).decode("utf-8")
        assert f"{part_names[-1]}#filepos999999" in penultimate_html

    # 10. Feature #14: Extract .mobi files from an input .zip archive
    input_zip = tmp_path / "books_bundle.zip"
    with zipfile.ZipFile(input_zip, "w") as zf:
        zf.write(sample_mobi, "Fantasy/sample_mobi6.mobi")
        zf.writestr("Fantasy/notes.txt", "ignore this text file")
        zf.writestr("__MACOSX/._sample_mobi6.mobi", b"ignore macos metadata")

    extracted_dir = tmp_path / "unzipped_mobis"
    extracted_items = epub_tools.extract_mobi_from_zip(input_zip, extracted_dir)
    assert len(extracted_items) == 1
    assert extracted_items[0]["fileName"] == "sample_mobi6.mobi"
    assert extracted_items[0]["relPath"] == "Fantasy/sample_mobi6.mobi"
    assert Path(extracted_items[0]["diskPath"]).exists()


def test_process_epub_features_omits_chapters_preview_by_default(tmp_path: Path):
    """Regression test: process_epub_features must omit chaptersPreview by default (include_preview=False)
    so _finalize_job's json.dumps never hits MemoryError on image-heavy books.
    """
    epub_tools = _load_bundle_module(tmp_path, "mobi2epub/epub_tools.py", "mobi2epub.epub_tools")
    from mobi2epub.engines.kindleunpack import KindleUnpackEngine

    sample_mobi = FIXTURES_DIR / "sample_mobi6.mobi"
    epub_path = tmp_path / "alice_default_preview.epub"
    conv = KindleUnpackEngine().convert(sample_mobi, epub_path)
    assert conv.success and epub_path.exists()

    # Default call (as used in _finalize_job during convert_one)
    report = epub_tools.process_epub_features(epub_path)
    assert report["chaptersPreview"] == []
    assert report["chapters"] == []
    assert "Alice" in (report["title"] or "")
    assert isinstance(report["toc"], list) and len(report["toc"]) >= 1
    assert report["healthReport"]["isValid"] is True

    # Explicit include_preview=True populates chaptersPreview
    report_with_preview = epub_tools.process_epub_features(epub_path, include_preview=True)
    assert len(report_with_preview["chaptersPreview"]) >= 1

    # Ensure default JSON serialization is much smaller than include_preview=True
    serialized = json.dumps(report)
    serialized_with_preview = json.dumps(report_with_preview)
    assert len(serialized) < 100 * 1024
    assert len(serialized) < len(serialized_with_preview) // 5


def test_process_epub_features_zero_rewrite_fast_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Regression test: when no modifications (css_preset='original', no overrides, no split needed)
    are requested, process_epub_features must NOT rewrite the .epub file on disk, while still
    accurately extracting title, coverDataUrl, toc, and healthReport.
    """
    epub_tools = _load_bundle_module(tmp_path, "mobi2epub/epub_tools.py", "mobi2epub.epub_tools")
    from mobi2epub.engines.kindleunpack import KindleUnpackEngine

    sample_mobi = FIXTURES_DIR / "sample_mobi6.mobi"
    epub_path = tmp_path / "alice_fastpath.epub"
    conv = KindleUnpackEngine().convert(sample_mobi, epub_path)
    assert conv.success and epub_path.exists()

    # Inject a cover image once so we can verify coverDataUrl extraction on the subsequent fast-path call
    cover_bytes = (DOCS_DIR / "icon-192.png").read_bytes()
    assert epub_tools.update_epub_metadata_and_cover(
        epub_path,
        cover_override={"bytes": cover_bytes, "mime": "image/png"},
    ) is True

    bytes_before = epub_path.read_bytes()

    # Guard against any archive rewrite during the fast-path call
    def _forbid_archive_update(*args, **kwargs):
        raise AssertionError("_update_epub_archive should not be called on the zero-rewrite fast path")

    monkeypatch.setattr(epub_tools, "_update_epub_archive", _forbid_archive_update)

    report = epub_tools.process_epub_features(
        epub_path,
        options={
            "cssPreset": "original",
            "autoSplitChapters": False,
            "metadataOverride": None,
            "coverFsInfo": None,
            "tocOverride": None,
        },
        include_preview=False,
    )

    assert epub_path.read_bytes() == bytes_before
    assert "Alice" in (report["title"] or "")
    assert report["coverDataUrl"] is not None
    assert report["coverDataUrl"].startswith("data:image/png;base64,")
    assert isinstance(report["toc"], list) and len(report["toc"]) >= 1
    assert report["healthReport"]["isValid"] is True
    assert report["healthReport"]["spineCount"] >= 1
    assert report["chaptersPreview"] == []


def test_read_epub_preview_caps_inlined_image_data(tmp_path: Path):
    """Regression test: read_epub_preview must cap per-image and cumulative Base64 image data
    so an image-heavy manga EPUB never produces an unbounded JSON payload.
    """
    epub_tools = _load_bundle_module(tmp_path, "mobi2epub/epub_tools.py", "mobi2epub.epub_tools")
    from mobi2epub.engines.kindleunpack import KindleUnpackEngine

    sample_mobi = FIXTURES_DIR / "sample_mobi6.mobi"
    epub_path = tmp_path / "manga_heavy.epub"
    conv = KindleUnpackEngine().convert(sample_mobi, epub_path)
    assert conv.success and epub_path.exists()

    # Inject 6 synthetic page images (50 KB each = 300 KB raw, ~400 KB base64) and a 200 KB oversized image
    img_tags = []
    replacements = {}
    png_header = (DOCS_DIR / "icon-192.png").read_bytes()

    for i in range(1, 7):
        arc_name = f"Images/page_{i:02d}.png"
        # Pad deterministic bytes to 50 KB per image
        payload = png_header + (b"\x00" * max(0, 50 * 1024 - len(png_header)))
        replacements[arc_name] = payload
        img_tags.append(f'<p><img src="{arc_name}" alt="Page {i}"/></p>')

    oversized_arc = "Images/giant_spread.png"
    replacements[oversized_arc] = png_header + (b"\x00" * (200 * 1024))
    img_tags.append(f'<p><img src="{oversized_arc}" alt="Giant Spread"/></p>')

    with zipfile.ZipFile(epub_path, "r") as zf:
        orig_xhtml = zf.read("book.xhtml").decode("utf-8", errors="replace")

    heavy_xhtml = orig_xhtml.replace("</body>", "".join(img_tags) + "</body>")
    replacements["book.xhtml"] = heavy_xhtml.encode("utf-8")
    assert epub_tools.replace_epub_files(epub_path, replacements) is True

    # Set tight caps: 100 KB max single image (so 200 KB giant_spread is skipped)
    # and 180 KB max cumulative base64 bytes (so only ~2 of the 50 KB images are inlined)
    max_single = 100 * 1024
    max_total = 180 * 1024
    preview_rep = epub_tools.read_epub_preview(
        epub_path,
        max_total_image_bytes=max_total,
        max_single_image_bytes=max_single,
    )

    chapters = preview_rep["chaptersPreview"]
    assert len(chapters) >= 1
    combined_html = "\n".join(ch["html"] for ch in chapters)

    inlined_data_urls = re.findall(r'src=["\'](data:image/[^"\']+)["\']', combined_html)
    total_inlined_chars = sum(len(url) for url in inlined_data_urls)

    assert len(inlined_data_urls) >= 1, "At least the first image within budget should be inlined"
    assert len(inlined_data_urls) <= 3, "Images exceeding the cumulative budget or single-image cap must be omitted"
    assert total_inlined_chars <= max_total

    # Verify JSON payload of chaptersPreview is strictly bounded well below raw image total (500 KB)
    preview_rep.pop("chapters", None)
    payload_json = json.dumps(preview_rep)
    assert len(payload_json) < max_total + 350 * 1024

