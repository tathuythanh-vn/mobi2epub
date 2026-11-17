/**
 * Web Worker for mobi2epub browser conversion engine (Pyodide + KindleUnpack + mobi2epub).
 * Runs 100% client-side in WebAssembly so the UI thread never blocks.
 */

const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/";
importScripts(`${PYODIDE_INDEX_URL}pyodide.js`);

let pyodide = null;
let initPromise = null;

function postStatus(phase, message) {
  self.postMessage({
    type: "init_status",
    phase,
    message,
  });
}

function toUint8Array(input) {
  if (!input) return null;
  if (input instanceof Uint8Array) return input;
  if (input instanceof ArrayBuffer) return new Uint8Array(input);
  if (ArrayBuffer.isView(input)) {
    return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
  }
  if (Array.isArray(input)) return new Uint8Array(input);
  return null;
}

/**
 * Read a file from Pyodide MEMFS as a standalone Uint8Array and immediately unlink it
 * from MEMFS so the file is never duplicated across MEMFS and multiple JS ArrayBuffers.
 */
function readAndUnlinkFsFile(py, filePath) {
  const raw = py.FS.readFile(filePath);
  try {
    py.FS.unlink(filePath);
  } catch (_) {
    // Ignore unlink error
  }
  if (raw.byteOffset === 0 && raw.byteLength === raw.buffer.byteLength) {
    return raw;
  }
  const copiedBuf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
  return new Uint8Array(copiedBuf);
}

/**
 * Clean up job workDir, any stray /tmp/mobiex* or /tmp/epub_* folders, temporary Python globals,
 * and run Python garbage collection (`gc.collect()`) after every worker job.
 */
async function cleanupWorkerJob(py, workDir, globalNames = []) {
  try {
    for (const name of globalNames) {
      try {
        py.globals.delete(name);
      } catch (_) {
        // Ignore
      }
    }
    py.globals.set("_cleanup_target_dir", workDir || "");
    await py.runPythonAsync(`
import gc
import os
import shutil

if _cleanup_target_dir and os.path.exists(_cleanup_target_dir):
    shutil.rmtree(_cleanup_target_dir, ignore_errors=True)

if os.path.isdir("/tmp"):
    for _entry in os.listdir("/tmp"):
        if _entry.startswith(("mobiex", "epub_")):
            shutil.rmtree(os.path.join("/tmp", _entry), ignore_errors=True)

gc.collect()
`);
    try {
      py.globals.delete("_cleanup_target_dir");
    } catch (_) {
      // Ignore
    }
  } catch (_) {
    // Ignore cleanup errors
  }
}

async function loadBundledPythonModules(py) {
  const pkgRoot = "/home/pyodide/pkgs";
  py.FS.mkdirTree(pkgRoot);

  // 1. Try fast single-request bundle.zip (contains mobi2epub, mobi, imghdr, loguru shim)
  try {
    const bundleUrl = new URL("./py/bundle.zip", self.location.href).toString();
    const resp = await fetch(bundleUrl);
    if (resp.ok) {
      const buf = await resp.arrayBuffer();
      py.unpackArchive(buf, "zip", { extractDir: pkgRoot });
      return;
    }
  } catch (err) {
    // Fallback to manifest loading below
  }

  // 2. Fallback: load individual Python files from ./py/manifest.json
  const manifestUrl = new URL("./py/manifest.json", self.location.href).toString();
  const manifestResp = await fetch(manifestUrl);
  if (!manifestResp.ok) {
    throw new Error(`Failed to fetch Python module manifest (${manifestResp.status})`);
  }
  const manifest = await manifestResp.json();
  for (const relPath of manifest.files || []) {
    const fileUrl = new URL(`./py/${relPath}`, self.location.href).toString();
    const res = await fetch(fileUrl);
    if (!res.ok) {
      throw new Error(`Failed to load ${relPath} (${res.status})`);
    }
    const text = await res.text();
    const fullPath = `${pkgRoot}/${relPath}`;
    const dirIdx = fullPath.lastIndexOf("/");
    if (dirIdx > 0) {
      py.FS.mkdirTree(fullPath.slice(0, dirIdx));
    }
    py.FS.writeFile(fullPath, text, { encoding: "utf8" });
  }
}

async function ensureInitialized() {
  if (pyodide) return pyodide;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    try {
      postStatus("loading", "Loading Pyodide WebAssembly Python runtime...");
      const py = await loadPyodide({
        indexURL: PYODIDE_INDEX_URL,
      });

      postStatus("packages", "Loading beautifulsoup4 & micropip packages...");
      await py.loadPackage(["beautifulsoup4", "micropip"]);

      postStatus("modules", "Loading mobi2epub & KindleUnpack conversion modules...");
      await loadBundledPythonModules(py);

      // Verify or install mobi via micropip if not already satisfied by bundle.zip
      await py.runPythonAsync(`
import sys
import os

pkg_root = "/home/pyodide/pkgs"
if pkg_root not in sys.path:
    sys.path.insert(0, pkg_root)

try:
    import mobi
except ImportError:
    import micropip
    await micropip.install("mobi")
    import mobi

from mobi2epub.precheck import check_mobi_file
from mobi2epub.engines.kindleunpack import KindleUnpackEngine
from mobi2epub.validate import validate_epub
from mobi2epub import epub_tools
`);

      pyodide = py;
      self.postMessage({
        type: "ready",
        engine: "KindleUnpack (Pyodide WASM)",
      });
      return py;
    } catch (err) {
      initPromise = null;
      const message = err && err.message ? err.message : String(err);
      self.postMessage({
        type: "init_error",
        message,
      });
      throw err;
    }
  })();

  return initPromise;
}

/**
 * Feature #13: Image Compression & E-Ink Grayscale Optimizer using OffscreenCanvas + createImageBitmap.
 */
async function optimizeEpubImagesInWorker(py, epubPath, imageOptimize) {
  if (!imageOptimize || !imageOptimize.enabled) return false;
  if (typeof OffscreenCanvas === "undefined" || typeof createImageBitmap !== "function") {
    return false;
  }

  const maxDim = Math.max(120, Number(imageOptimize.maxDim) || 1200);
  let rawQuality = Number(imageOptimize.quality);
  if (!Number.isFinite(rawQuality) || rawQuality <= 0) rawQuality = 0.75;
  if (rawQuality > 1) rawQuality = rawQuality / 100;
  const quality = Math.min(0.98, Math.max(0.1, rawQuality));
  const grayscale = Boolean(imageOptimize.grayscale);

  const extractDir = `${epubPath}_imgopt`;
  py.FS.mkdirTree(extractDir);

  try {
    py.globals.set("_imgopt_epub", epubPath);
    py.globals.set("_imgopt_dir", extractDir);
    const listJson = await py.runPythonAsync(`
import json
import zipfile
from mobi2epub.epub_tools import list_epub_images

imgs = list_epub_images(_imgopt_epub)
with zipfile.ZipFile(_imgopt_epub, "r") as zf:
    for item in imgs:
        zf.extract(item["arcName"], _imgopt_dir)
json.dumps(imgs)
`);

    const images = JSON.parse(listJson || "[]");
    if (!images.length) return false;

    const modifiedArcs = [];

    for (const item of images) {
      const diskPath = `${extractDir}/${item.arcName}`;
      let origBytes;
      try {
        origBytes = py.FS.readFile(diskPath);
      } catch (_) {
        continue;
      }

      let keptModified = false;
      try {
        const blob = new Blob([origBytes], { type: item.mime || "image/jpeg" });
        const bmp = await createImageBitmap(blob);
        let targetW = bmp.width;
        let targetH = bmp.height;
        const needsResize = targetW > maxDim || targetH > maxDim;

        if (needsResize) {
          if (targetW >= targetH) {
            targetH = Math.max(1, Math.round((targetH * maxDim) / targetW));
            targetW = maxDim;
          } else {
            targetW = Math.max(1, Math.round((targetW * maxDim) / targetH));
            targetH = maxDim;
          }
        }

        const canvas = new OffscreenCanvas(targetW, targetH);
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, targetW, targetH);
        if (grayscale) {
          try {
            ctx.filter = "grayscale(100%)";
          } catch (_) {
            // Fallback pixel luminance conversion below
          }
        }
        ctx.drawImage(bmp, 0, 0, targetW, targetH);
        if (typeof bmp.close === "function") bmp.close();

        if (grayscale) {
          try {
            const imgData = ctx.getImageData(0, 0, targetW, targetH);
            const d = imgData.data;
            for (let i = 0; i < d.length; i += 4) {
              const lum = Math.round(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]);
              d[i] = lum;
              d[i + 1] = lum;
              d[i + 2] = lum;
            }
            ctx.putImageData(imgData, 0, 0);
          } catch (_) {
            // Ignore getImageData errors
          }
        }

        const outMime = item.arcName.toLowerCase().endsWith(".png") && !grayscale && !needsResize
          ? "image/png"
          : "image/jpeg";
        const outBlob = await canvas.convertToBlob({ type: outMime, quality });
        const outBuf = await outBlob.arrayBuffer();
        const outUint8 = new Uint8Array(outBuf);

        if (grayscale || needsResize || outUint8.byteLength < origBytes.byteLength) {
          py.FS.writeFile(diskPath, outUint8);
          modifiedArcs.push(item.arcName);
          keptModified = true;
        }
      } catch (_) {
        // Skip individual image if decoding fails
      }

      if (!keptModified) {
        try {
          py.FS.unlink(diskPath);
        } catch (_) {
          // Ignore unlink error
        }
      }
    }

    if (modifiedArcs.length > 0) {
      py.globals.set("_imgopt_modified", JSON.stringify(modifiedArcs));
      await py.runPythonAsync(`
import json
from pathlib import Path
from mobi2epub.epub_tools import replace_epub_files

arcs = json.loads(_imgopt_modified)
replacements = {}
for arc in arcs:
    p = Path(_imgopt_dir) / arc
    if p.exists():
        replacements[arc] = p.read_bytes()
        try:
            p.unlink()
        except OSError:
            pass
replace_epub_files(_imgopt_epub, replacements)
del replacements
`);
      return true;
    }
    return false;
  } finally {
    await cleanupWorkerJob(py, extractDir, ["_imgopt_epub", "_imgopt_dir", "_imgopt_modified"]);
  }
}

function prepareCoverOverrideInFs(py, workDir, coverOverride) {
  if (!coverOverride) return null;
  if (typeof coverOverride === "string" && coverOverride.startsWith("data:")) {
    return { dataUrl: coverOverride };
  }
  const rawBytes = toUint8Array(coverOverride.bytes || coverOverride.data || coverOverride);
  if (rawBytes && rawBytes.byteLength > 0) {
    const coverFile = `${workDir}/_custom_cover.bin`;
    py.FS.writeFile(coverFile, rawBytes);
    return {
      diskPath: coverFile,
      mime: coverOverride.mime || "image/jpeg",
    };
  }
  if (coverOverride.dataUrl || coverOverride.base64) {
    return {
      dataUrl: coverOverride.dataUrl || coverOverride.base64,
      mime: coverOverride.mime || "image/jpeg",
    };
  }
  return null;
}

async function handleConvert(msg) {
  const responseType = msg.type === "convert_one" ? "convert_result" : "file_result";
  const { id, fileName, relPath } = msg;
  const options = msg.options || {};
  const cssPreset = options.cssPreset ?? msg.cssPreset ?? "original";
  const autoSplitChapters = Boolean(options.autoSplitChapters ?? msg.autoSplitChapters ?? false);
  const imageOptimize = options.imageOptimize ?? msg.imageOptimize ?? null;
  const metadataOverride = options.metadataOverride ?? msg.metadataOverride ?? null;
  const coverOverride = options.coverOverride ?? msg.coverOverride ?? null;
  const tocOverride = options.tocOverride ?? msg.tocOverride ?? null;

  const py = await ensureInitialized();
  const workDir = `/tmp/mobi2epub_job_${id || Date.now()}`;
  py.FS.mkdirTree(workDir);

  const safeInputName = (fileName || "input.mobi").replace(/[^a-zA-Z0-9._-]/g, "_");
  const stem = safeInputName.replace(/\.[^.]+$/, "") || "book";
  const srcPath = `${workDir}/${safeInputName}`;
  const dstPath = `${workDir}/${stem}.epub`;

  try {
    const inputBytes = toUint8Array(msg.bytes || msg.data || msg.mobiBytes || msg.buffer);
    if (!inputBytes) {
      throw new Error("No input MOBI bytes provided");
    }
    const originalSize = inputBytes.byteLength;
    py.FS.writeFile(srcPath, inputBytes);

    // Drop JS references to input buffer immediately after writing to MEMFS
    msg.bytes = null;
    msg.data = null;
    msg.mobiBytes = null;
    msg.buffer = null;

    const coverFsInfo = prepareCoverOverrideInFs(py, workDir, coverOverride);

    py.globals.set("_job_src", srcPath);
    py.globals.set("_job_dst", dstPath);
    py.globals.set(
      "_job_opts_json",
      JSON.stringify({
        cssPreset,
        autoSplitChapters,
        metadataOverride,
        coverFsInfo,
        tocOverride,
      })
    );

    const step1Json = await py.runPythonAsync(`
import json
from pathlib import Path
from mobi2epub.precheck import check_mobi_file
from mobi2epub.engines.kindleunpack import KindleUnpackEngine
from mobi2epub.epub_tools import normalize_epub_ncx_links

def _run_step1(src_str, dst_str):
    src = Path(src_str)
    dst = Path(dst_str)

    pre = check_mobi_file(src)
    if not pre.is_valid:
        try:
            src.unlink(missing_ok=True)
        except OSError:
            pass
        return json.dumps({
            "success": False,
            "error_type": "corrupt",
            "error_message": pre.error_reason or "Corrupt or invalid MOBI file",
            "title": pre.title,
            "version": pre.version,
        })

    if pre.is_drm:
        try:
            src.unlink(missing_ok=True)
        except OSError:
            pass
        return json.dumps({
            "success": False,
            "error_type": "drm",
            "error_message": pre.error_reason or "DRM protected: book is encrypted and cannot be converted",
            "title": pre.title,
            "version": pre.version,
        })

    engine = KindleUnpackEngine()
    res = engine.convert(src, dst)

    # Immediately unlink input .mobi from MEMFS once extraction/conversion finishes
    try:
        src.unlink(missing_ok=True)
    except OSError:
        pass

    if not res.success:
        return json.dumps({
            "success": False,
            "error_type": res.error_type or "conversion_failed",
            "error_message": res.error_message or "Conversion failed",
            "title": res.title or pre.title,
            "version": pre.version,
        })

    normalize_epub_ncx_links(dst)

    return json.dumps({
        "success": True,
        "pre_title": pre.title,
        "pre_version": pre.version,
    })

_run_step1(_job_src, _job_dst)
`);

    const step1 = JSON.parse(step1Json);
    if (!step1.success) {
      self.postMessage({
        type: responseType,
        id,
        ok: false,
        success: false,
        fileName,
        relPath: relPath || fileName,
        errorType: step1.error_type || "conversion_failed",
        errorMessage: step1.error_message || "Conversion failed",
        title: step1.title || null,
        originalSize,
      });
      return;
    }

    // Apply optional features & extract lightweight report (include_preview=False, zero-rewrite fast path)
    py.globals.set("_job_dst", dstPath);
    const reportJson = await py.runPythonAsync(`
import json
from pathlib import Path
from mobi2epub.validate import validate_epub
from mobi2epub.epub_tools import process_epub_features

def _finalize_job(dst_str, opts_str):
    dst = Path(dst_str)
    opts = json.loads(opts_str)
    rep = process_epub_features(
        dst,
        options=opts,
        include_preview=False,
    )
    val = validate_epub(dst)
    if not val.is_valid:
        return json.dumps({
            "valid": False,
            "error_message": f"Output EPUB validation failed: {val.error_summary}",
        })
    rep["valid"] = True
    return json.dumps(rep)

_finalize_job(_job_dst, _job_opts_json)
`);

    const report = JSON.parse(reportJson);
    if (!report.valid) {
      self.postMessage({
        type: responseType,
        id,
        ok: false,
        success: false,
        fileName,
        relPath: relPath || fileName,
        errorType: "validation_error",
        errorMessage: report.error_message || "Output EPUB validation failed",
        title: step1.pre_title || null,
        originalSize,
      });
      return;
    }

    // Optional Feature #13: OffscreenCanvas image optimization
    if (imageOptimize && imageOptimize.enabled) {
      await optimizeEpubImagesInWorker(py, dstPath, imageOptimize);
    }

    const outBytesView = readAndUnlinkFsFile(py, dstPath);
    const outBuffer = outBytesView.buffer;

    const baseRel = (relPath || fileName || "book.mobi").replace(/\.[^/.]+$/, "");
    const outRelPath = `${baseRel}.epub`;
    const outFileName = outRelPath.split("/").pop();
    const finalTitle = report.title || step1.pre_title || stem;

    self.postMessage(
      {
        type: responseType,
        id,
        ok: true,
        success: true,
        fileName,
        relPath: relPath || fileName,
        outFileName,
        outRelPath,
        title: finalTitle,
        author: report.author || "",
        language: report.language || "en",
        publisher: report.publisher || "",
        description: report.description || "",
        coverDataUrl: report.coverDataUrl || null,
        originalSize,
        epubSize: outBuffer.byteLength,
        size: outBuffer.byteLength,
        version: report.version || step1.pre_version || "2.0",
        spineCount: report.spineCount || 0,
        healthReport: report.healthReport,
        toc: report.toc || [],
        chaptersPreview: [],
        chapters: [],
        epubBytes: outBytesView,
        epubData: outBuffer,
        errorType: null,
        errorMessage: null,
      },
      [outBuffer]
    );
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    self.postMessage({
      type: responseType,
      id,
      ok: false,
      success: false,
      fileName,
      relPath: relPath || fileName,
      errorType: "exception",
      errorMessage: message,
      title: null,
    });
  } finally {
    await cleanupWorkerJob(py, workDir, ["_job_src", "_job_dst", "_job_opts_json"]);
  }
}

/**
 * Feature #8 & #9: Fast in-place EPUB metadata, cover, TOC, and CSS update (<0.1s).
 */
async function handleUpdateEpub(msg) {
  const { id } = msg;
  const options = msg.options || {};
  const metadataOverride = msg.metadataOverride ?? options.metadataOverride ?? msg.metadata ?? null;
  const coverOverride = msg.coverOverride ?? options.coverOverride ?? msg.cover ?? null;
  const tocOverride = msg.tocOverride ?? options.tocOverride ?? msg.toc ?? null;
  const cssPreset = msg.cssPreset ?? options.cssPreset ?? null;
  const imageOptimize = msg.imageOptimize ?? options.imageOptimize ?? null;

  const py = await ensureInitialized();
  const workDir = `/tmp/mobi2epub_upd_${id || Date.now()}`;
  py.FS.mkdirTree(workDir);
  const epubPath = `${workDir}/book.epub`;

  try {
    const inputBytes = toUint8Array(msg.epubBytes || msg.epubData || msg.bytes || msg.data);
    if (!inputBytes) {
      throw new Error("No EPUB bytes provided to update_epub");
    }
    py.FS.writeFile(epubPath, inputBytes);
    msg.epubBytes = null;
    msg.epubData = null;
    msg.bytes = null;
    msg.data = null;

    const coverFsInfo = prepareCoverOverrideInFs(py, workDir, coverOverride);

    py.globals.set("_upd_epub", epubPath);
    py.globals.set(
      "_upd_opts_json",
      JSON.stringify({
        metadataOverride,
        coverFsInfo,
        tocOverride,
        cssPreset,
      })
    );

    await py.runPythonAsync(`
import json
from pathlib import Path
from mobi2epub.epub_tools import update_epub_metadata_and_cover, inject_custom_css

def _apply_updates(epub_str, opts_str):
    dst = Path(epub_str)
    opts = json.loads(opts_str)
    meta_ov = opts.get("metadataOverride")
    toc_ov = opts.get("tocOverride")
    cover_info = opts.get("coverFsInfo")
    cover_ov = None
    if cover_info:
        if cover_info.get("diskPath"):
            cover_ov = {
                "diskPath": cover_info["diskPath"],
                "mime": cover_info.get("mime") or "image/jpeg",
            }
        elif cover_info.get("dataUrl"):
            cover_ov = {
                "dataUrl": cover_info["dataUrl"],
                "mime": cover_info.get("mime") or "image/jpeg",
            }
    update_epub_metadata_and_cover(dst, meta_ov, cover_ov, toc_ov)
    css_preset = opts.get("cssPreset")
    if css_preset and css_preset != "original":
        inject_custom_css(dst, css_preset)

_apply_updates(_upd_epub, _upd_opts_json)
`);

    if (imageOptimize && imageOptimize.enabled) {
      await optimizeEpubImagesInWorker(py, epubPath, imageOptimize);
    }

    py.globals.set("_upd_epub", epubPath);
    const reportJson = await py.runPythonAsync(`
import json
from mobi2epub.epub_tools import build_full_epub_report
json.dumps(build_full_epub_report(_upd_epub, include_preview=False))
`);
    const report = JSON.parse(reportJson);

    const outBytesView = readAndUnlinkFsFile(py, epubPath);
    const outBuffer = outBytesView.buffer;

    self.postMessage(
      {
        type: "update_epub_result",
        id,
        ok: true,
        success: true,
        epubBytes: outBytesView,
        epubData: outBuffer,
        epubSize: outBuffer.byteLength,
        size: outBuffer.byteLength,
        title: report.title || null,
        author: report.author || "",
        language: report.language || "en",
        publisher: report.publisher || "",
        description: report.description || "",
        coverDataUrl: report.coverDataUrl || null,
        healthReport: report.healthReport,
        toc: report.toc || [],
        chaptersPreview: null,
        chapters: null,
        errorType: null,
        errorMessage: null,
      },
      [outBuffer]
    );
  } catch (err) {
    self.postMessage({
      type: "update_epub_result",
      id,
      ok: false,
      success: false,
      errorType: "update_error",
      errorMessage: err && err.message ? err.message : String(err),
    });
  } finally {
    await cleanupWorkerJob(py, workDir, ["_upd_epub", "_upd_opts_json"]);
  }
}

/**
 * Feature #6: On-demand EPUB reader inspection (`read_epub`).
 */
async function handleReadEpub(msg) {
  const { id } = msg;
  const py = await ensureInitialized();
  const workDir = `/tmp/mobi2epub_read_${id || Date.now()}`;
  py.FS.mkdirTree(workDir);
  const epubPath = `${workDir}/book.epub`;

  try {
    const inputBytes = toUint8Array(msg.epubBytes || msg.epubData || msg.bytes || msg.data);
    if (!inputBytes) {
      throw new Error("No EPUB bytes provided to read_epub");
    }
    const inputByteLen = inputBytes.byteLength;
    py.FS.writeFile(epubPath, inputBytes);
    msg.epubBytes = null;
    msg.epubData = null;
    msg.bytes = null;
    msg.data = null;

    py.globals.set("_read_epub_path", epubPath);
    const reportJson = await py.runPythonAsync(`
import json
import os
from mobi2epub.epub_tools import read_epub_preview

_rep = read_epub_preview(_read_epub_path)
_rep.pop("chapters", None)
try:
    os.remove(_read_epub_path)
except OSError:
    pass
json.dumps(_rep)
`);
    const report = JSON.parse(reportJson);

    self.postMessage({
      type: "read_epub_result",
      id,
      ok: true,
      success: true,
      title: report.title || null,
      author: report.author || "",
      language: report.language || "en",
      publisher: report.publisher || "",
      description: report.description || "",
      coverDataUrl: report.coverDataUrl || null,
      epubSize: report.epubSize || inputByteLen,
      healthReport: report.healthReport,
      toc: report.toc || [],
      chapters: report.chaptersPreview || [],
      chaptersPreview: report.chaptersPreview || [],
      errorType: null,
      errorMessage: null,
    });
  } catch (err) {
    self.postMessage({
      type: "read_epub_result",
      id,
      ok: false,
      success: false,
      errorType: "read_error",
      errorMessage: err && err.message ? err.message : String(err),
    });
  } finally {
    await cleanupWorkerJob(py, workDir, ["_read_epub_path", "_rep"]);
  }
}

/**
 * Feature #14: Extract .mobi/.prc/.azw3/.azw files from an input .zip archive (`extract_input_zip`).
 */
async function handleExtractInputZip(msg) {
  const { id, fileName } = msg;
  const py = await ensureInitialized();
  const workDir = `/tmp/mobi2epub_inzip_${id || Date.now()}`;
  py.FS.mkdirTree(workDir);
  const zipPath = `${workDir}/input.zip`;
  const outDir = `${workDir}/extracted`;

  try {
    const zipBytes = toUint8Array(msg.zipBytes || msg.zipData || msg.bytes || msg.data);
    if (!zipBytes) {
      throw new Error("No ZIP bytes provided to extract_input_zip");
    }
    py.FS.writeFile(zipPath, zipBytes);
    msg.zipBytes = null;
    msg.zipData = null;
    msg.bytes = null;
    msg.data = null;

    py.globals.set("_inzip_path", zipPath);
    py.globals.set("_inzip_out", outDir);

    const extractedJson = await py.runPythonAsync(`
import json
import os
from mobi2epub.epub_tools import extract_mobi_from_zip

_extracted_items = extract_mobi_from_zip(_inzip_path, _inzip_out)
try:
    os.remove(_inzip_path)
except OSError:
    pass
json.dumps(_extracted_items)
`);

    const items = JSON.parse(extractedJson || "[]");
    const filesOut = [];
    const transfers = [];

    for (const item of items) {
      const fileUint8 = readAndUnlinkFsFile(py, item.diskPath);
      const buf = fileUint8.buffer;
      transfers.push(buf);
      filesOut.push({
        fileName: item.fileName,
        name: item.fileName,
        relPath: item.relPath,
        bytes: fileUint8,
        data: buf,
        size: buf.byteLength,
      });
    }

    self.postMessage(
      {
        type: "extract_input_zip_result",
        id,
        ok: true,
        success: true,
        fileName: fileName || "archive.zip",
        files: filesOut,
        errorMessage: null,
      },
      transfers
    );
  } catch (err) {
    self.postMessage({
      type: "extract_input_zip_result",
      id,
      ok: false,
      success: false,
      fileName: fileName || "archive.zip",
      files: [],
      errorMessage: err && err.message ? err.message : String(err),
    });
  } finally {
    await cleanupWorkerJob(py, workDir, ["_inzip_path", "_inzip_out", "_extracted_items"]);
  }
}

async function handleCreateZip(msg) {
  const { id, files } = msg;
  const py = await ensureInitialized();
  const zipWorkDir = `/tmp/mobi2epub_zip_${id || Date.now()}`;
  py.FS.mkdirTree(zipWorkDir);
  const zipOutPath = `${zipWorkDir}/converted_epubs.zip`;

  try {
    const manifest = [];
    for (let i = 0; i < (files || []).length; i++) {
      const item = files[i];
      const tempItemPath = `${zipWorkDir}/item_${i}.epub`;
      const rawBytes = toUint8Array(item.bytes || item.data || item.epubBytes || item.epubData);
      if (!rawBytes) continue;
      py.FS.writeFile(tempItemPath, rawBytes);
      item.bytes = null;
      item.data = null;
      item.epubBytes = null;
      item.epubData = null;
      manifest.push({
        diskPath: tempItemPath,
        arcName: item.arcName || item.relPath || item.name || item.fileName || `book_${i + 1}.epub`,
      });
    }

    py.globals.set("_zip_manifest_json", JSON.stringify(manifest));
    py.globals.set("_zip_out_path", zipOutPath);

    await py.runPythonAsync(`
import json
import os
import zipfile

items = json.loads(_zip_manifest_json)
used_names = set()
with zipfile.ZipFile(_zip_out_path, "w", compression=zipfile.ZIP_STORED) as zf:
    for item in items:
        arc = item["arcName"].lstrip("/\\\\")
        base_arc = arc
        counter = 2
        while arc in used_names:
            if "." in base_arc:
                stem, ext = base_arc.rsplit(".", 1)
                arc = f"{stem}_{counter}.{ext}"
            else:
                arc = f"{base_arc}_{counter}"
            counter += 1
        used_names.add(arc)
        zf.write(item["diskPath"], arc)
        try:
            os.remove(item["diskPath"])
        except OSError:
            pass
`);

    const zipBytesView = readAndUnlinkFsFile(py, zipOutPath);
    const zipBuffer = zipBytesView.buffer;

    self.postMessage(
      {
        type: "zip_result",
        id,
        ok: true,
        success: true,
        zipBytes: zipBytesView,
        zipData: zipBuffer,
      },
      [zipBuffer]
    );
  } catch (err) {
    self.postMessage({
      type: "zip_result",
      id,
      ok: false,
      success: false,
      errorMessage: err && err.message ? err.message : String(err),
    });
  } finally {
    await cleanupWorkerJob(py, zipWorkDir, ["_zip_manifest_json", "_zip_out_path"]);
  }
}

self.onmessage = async (event) => {
  const msg = event.data;
  if (!msg || !msg.type) return;

  if (msg.type === "init") {
    try {
      await ensureInitialized();
    } catch (_) {
      // Error already posted via init_error
    }
  } else if (msg.type === "convert_one" || msg.type === "convert_file") {
    await handleConvert(msg);
  } else if (msg.type === "update_epub") {
    await handleUpdateEpub(msg);
  } else if (msg.type === "read_epub") {
    await handleReadEpub(msg);
  } else if (msg.type === "extract_input_zip") {
    await handleExtractInputZip(msg);
  } else if (msg.type === "create_zip" || msg.type === "make_zip") {
    await handleCreateZip(msg);
  }
};
