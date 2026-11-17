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

async function handleConvertFile(msg) {
  const { id, fileName, relPath, data } = msg;
  const py = await ensureInitialized();

  const workDir = `/tmp/mobi2epub_job_${id}`;
  py.FS.mkdirTree(workDir);

  const safeInputName = (fileName || "input.mobi").replace(/[^a-zA-Z0-9._-]/g, "_");
  const stem = safeInputName.replace(/\.[^.]+$/, "") || "book";
  const srcPath = `${workDir}/${safeInputName}`;
  const dstPath = `${workDir}/${stem}.epub`;

  try {
    const inputBytes = new Uint8Array(data);
    py.FS.writeFile(srcPath, inputBytes);

    py.globals.set("_job_src", srcPath);
    py.globals.set("_job_dst", dstPath);

    const resultProxy = await py.runPythonAsync(`
import json
from pathlib import Path
from mobi2epub.precheck import check_mobi_file
from mobi2epub.engines.kindleunpack import KindleUnpackEngine
from mobi2epub.validate import validate_epub

def _run_conversion(src_str, dst_str):
    src = Path(src_str)
    dst = Path(dst_str)

    pre = check_mobi_file(src)
    if not pre.is_valid:
        return json.dumps({
            "success": False,
            "error_type": "corrupt",
            "error_message": pre.error_reason or "Corrupt or invalid MOBI file",
            "title": pre.title,
            "version": pre.version,
        })

    if pre.is_drm:
        return json.dumps({
            "success": False,
            "error_type": "drm",
            "error_message": pre.error_reason or "DRM protected: book is encrypted and cannot be converted",
            "title": pre.title,
            "version": pre.version,
        })

    engine = KindleUnpackEngine()
    res = engine.convert(src, dst)
    if not res.success:
        return json.dumps({
            "success": False,
            "error_type": res.error_type or "conversion_failed",
            "error_message": res.error_message or "Conversion failed",
            "title": res.title or pre.title,
            "version": pre.version,
        })

    val = validate_epub(dst)
    if not val.is_valid:
        return json.dumps({
            "success": False,
            "error_type": "validation_error",
            "error_message": f"Output EPUB validation failed: {val.error_summary}",
            "title": val.title or res.title or pre.title,
            "version": pre.version,
        })

    return json.dumps({
        "success": True,
        "error_type": None,
        "error_message": None,
        "title": val.title or res.title or pre.title,
        "version": pre.version,
        "spine_count": val.spine_items_count,
    })

_run_conversion(_job_src, _job_dst)
`);

    const parsed = JSON.parse(resultProxy);

    if (parsed.success) {
      const epubUint8 = py.FS.readFile(dstPath);
      const outBuffer = epubUint8.buffer.slice(
        epubUint8.byteOffset,
        epubUint8.byteOffset + epubUint8.byteLength
      );

      const baseRel = (relPath || fileName || "book.mobi").replace(/\.[^/.]+$/, "");
      const outRelPath = `${baseRel}.epub`;
      const outFileName = outRelPath.split("/").pop();

      self.postMessage(
        {
          type: "file_result",
          id,
          success: true,
          fileName,
          relPath: relPath || fileName,
          outFileName,
          outRelPath,
          title: parsed.title || null,
          version: parsed.version || null,
          spineCount: parsed.spine_count || 0,
          epubData: outBuffer,
        },
        [outBuffer]
      );
    } else {
      self.postMessage({
        type: "file_result",
        id,
        success: false,
        fileName,
        relPath: relPath || fileName,
        errorType: parsed.error_type || "conversion_failed",
        errorMessage: parsed.error_message || "Conversion failed",
        title: parsed.title || null,
      });
    }
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    self.postMessage({
      type: "file_result",
      id,
      success: false,
      fileName,
      relPath: relPath || fileName,
      errorType: "exception",
      errorMessage: message,
      title: null,
    });
  } finally {
    try {
      py.globals.set("_cleanup_dir", workDir);
      await py.runPythonAsync(`
import shutil
shutil.rmtree(_cleanup_dir, ignore_errors=True)
`);
    } catch (_) {
      // Ignore cleanup errors
    }
  }
}

async function handleCreateZip(msg) {
  const { id, files } = msg;
  const py = await ensureInitialized();
  const zipWorkDir = `/tmp/mobi2epub_zip_${id}`;
  py.FS.mkdirTree(zipWorkDir);
  const zipOutPath = `${zipWorkDir}/converted_epubs.zip`;

  try {
    const manifest = [];
    for (let i = 0; i < files.length; i++) {
      const item = files[i];
      const tempItemPath = `${zipWorkDir}/item_${i}.epub`;
      py.FS.writeFile(tempItemPath, new Uint8Array(item.data));
      manifest.push({
        diskPath: tempItemPath,
        arcName: item.arcName || item.name || `book_${i + 1}.epub`,
      });
    }

    py.globals.set("_zip_manifest_json", JSON.stringify(manifest));
    py.globals.set("_zip_out_path", zipOutPath);

    await py.runPythonAsync(`
import json
import zipfile

items = json.loads(_zip_manifest_json)
used_names = set()
with zipfile.ZipFile(_zip_out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
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
`);

    const zipUint8 = py.FS.readFile(zipOutPath);
    const zipBuffer = zipUint8.buffer.slice(
      zipUint8.byteOffset,
      zipUint8.byteOffset + zipUint8.byteLength
    );

    self.postMessage(
      {
        type: "zip_result",
        id,
        success: true,
        zipData: zipBuffer,
      },
      [zipBuffer]
    );
  } catch (err) {
    self.postMessage({
      type: "zip_result",
      id,
      success: false,
      errorMessage: err && err.message ? err.message : String(err),
    });
  } finally {
    try {
      py.globals.set("_cleanup_zip_dir", zipWorkDir);
      await py.runPythonAsync(`
import shutil
shutil.rmtree(_cleanup_zip_dir, ignore_errors=True)
`);
    } catch (_) {
      // Ignore cleanup errors
    }
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
  } else if (msg.type === "convert_file") {
    await handleConvertFile(msg);
  } else if (msg.type === "create_zip") {
    await handleCreateZip(msg);
  }
};
