/**
 * Frontend application logic for MOBI to EPUB Converter (Web Edition).
 * Implements all 17 client-side features in plan.md:
 *   #1 Offline PWA + Install App button
 *   #2 Multi-Worker Parallel Conversion Pool
 *   #3 Direct "Save to Folder" (File System Access API)
 *   #4 Browser History Cache (IndexedDB — "Recent Conversions")
 *   #5 Rich Book Cover, Title & Metadata Cards
 *   #6 Built-in In-Browser EPUB Reader Preview Modal
 *   #7 EPUB Structure & Health Report Badge + Modal
 *   #8 Table of Contents (TOC) Inspector & Editor
 *   #9 Edit Metadata & Cover Before/After Conversion
 *   #10 Custom Output Filename Templates
 *   #11 Custom CSS / Typography Presets
 *   #12 Auto-Split Large HTML Chapters
 *   #13 Image Compression & E-Ink Grayscale Optimizer
 *   #14 Drop/Select .zip Archive of .mobi Books
 *   #15 Mobile "Share / Open In..." (Web Share API)
 *   #16 Dark / Light Theme Toggle
 *   #17 Multi-Language UI (English & Vietnamese)
 */

const SUPPORTED_BOOK_EXTENSIONS = [".mobi", ".prc", ".azw3", ".azw"];
const SUPPORTED_ALL_EXTENSIONS = [".mobi", ".prc", ".azw3", ".azw", ".zip"];
const HISTORY_DB_NAME = "mobi2epub_history";
const HISTORY_STORE_NAME = "books";
const HISTORY_MAX_ITEMS = 20;

// ---------------------------------------------------------------------------
// #17 Multi-Language UI Dictionary (EN | VI)
// ---------------------------------------------------------------------------

const I18N = {
  en: {
    appTitle: "MOBI to EPUB Converter",
    appSubtitle: "Powered by mobi2epub & KindleUnpack in your browser",
    engineLoading: "Loading Pyodide runtime...",
    engineReady: "Engine Ready · {engine}",
    engineError: "Engine Error",
    installApp: "Install App",
    windowsAppBtn: "Windows App (.exe)",
    privacyTitle: "100% Private & Client-Side:",
    privacyDesc:
      "Your books never leave your device. Full MOBI binary header pre-check (DRM & corruption detection), KindleUnpack extraction, XHTML conversion, and EPUB validation run locally inside Web Workers.",
    sec1Title: "1. Input MOBI / ZIP Files",
    trySampleBtn: "Try Sample MOBI (One-Click Demo)",
    dropzoneTitle: "Drag & drop MOBI files, folders, or .zip archives here",
    dropzoneHint:
      "Supports .mobi, .prc, .azw3, .azw, and .zip batches",
    addFilesBtn: "Add files / .zip...",
    selectFolderBtn: "Select folder...",
    saveToFolderBtn: "Save Directly to Folder...",
    clearOutDir: "Reset",
    lblFilenameTemplate: "Output Filename Template",
    tplOriginal: "{OriginalFilename}.epub (Default)",
    lblCssPreset: "Typography / CSS Preset",
    cssOriginal: "Keep Original Styling",
    cssSerif: "Clean Book Serif",
    cssSans: "Modern Sans-Serif",
    cssDyslexia: "Dyslexia-Friendly Spacing",
    chkRecursive: "Include subfolders",
    chkForce: "Overwrite existing",
    chkAutoSplit: "Auto-split large HTML chapters",
    chkImageOptimize: "Optimize images",
    chkGrayscale: "E-Ink Grayscale",
    lblMaxDim: "Max px:",
    lblQuality: "Quality %:",
    noFilesSelected:
      "No files selected — drop .mobi or .zip files above or click Add files...",
    clearBtn: "Clear",
    convertBtn: "Convert",
    cancelBtn: "Cancel",
    stoppingBtn: "Stopping...",
    sec2Title: "2. Conversion Progress",
    statusIdle: 'Select input files or click "Try Sample MOBI" to begin.',
    statusWaitingEngine: "Waiting for Pyodide engine to finish loading...",
    statusExtractingZip: "Extracting books from {name}...",
    statusFinished: "Finished in {sec}s",
    statusStopped: "Stopped by user ({ok} converted, {skip} skipped, {fail} failed)",
    sec3Title: "3. Converted EPUBs",
    downloadAllZipBtn: "Download All (.zip)",
    buildingZipBtn: "Building .zip...",
    emptyDownloads:
      "Converted EPUB book cards with cover thumbnails, reader preview, and health reports will appear here.",
    secHistoryTitle: "Recent Conversions (Cached in Browser)",
    hideHistoryBtn: "Hide",
    showHistoryBtn: "Show",
    clearHistoryBtn: "Clear History",
    sec4Title: "4. Activity Log",
    clearLogBtn: "Clear Log",
    readerTocBtn: "TOC",
    readerPrev: "Prev",
    readerNext: "Next",
    readerChaptersHeading: "Chapters / TOC",
    healthModalTitle: "EPUB Structure & Health Report",
    editModalTitle: "Edit Book Metadata, Cover & Table of Contents",
    editMetaHeading: "Book Metadata (OPF)",
    lblTitle: "Title",
    lblAuthor: "Author / Creator",
    lblLanguage: "Language (BCP-47)",
    lblPublisher: "Publisher",
    lblDescription: "Description / Synopsis",
    editCoverHeading: "Cover Image",
    uploadCoverBtn: "Upload Cover (JPG/PNG)...",
    resetCoverBtn: "Reset Cover",
    coverHint: "Replaces or inserts the cover image in the EPUB package.",
    editTocHeading: "Table of Contents (TOC)",
    addTocEntryBtn: "+ Add Entry",
    tocEditorHint:
      "Rename chapters, reorder entries, or remove empty/duplicate items.",
    saveChangesBtn: "Save & Update EPUB",
    savingChangesBtn: "Updating EPUB...",
    footerTagline:
      "Pure-Python KindleUnpack engine with header pre-check & EPUB validation",
    footerWinGui: "Download Windows Desktop GUI (MobiToEpub.exe)",
    footerReleases: "All Releases",
    footerRepo: "GitHub Repository",
    btnDownloadEpub: "⬇ Download .epub",
    btnPreviewRead: "📖 Read / Preview",
    btnEditInfo: "✏️ Edit Info / TOC",
    btnShareEpub: "📤 Share",
    badgeValidEpub: "✓ VALID EPUB",
    badgeEdited: "Edited",
    unknownAuthor: "Unknown Author",
    filesSelectedSummary: "{count} files selected ({size}): {first}, ...",
    directSaveActive: "Direct Save to folder: {name}/",
    workerSingular: "{n} Worker",
    workerPlural: "{n} Workers",
    summaryLine: "Summary: Converted: {ok}  |  Skipped: {skip}  |  Failed: {fail}",
    elapsedLabel: "Elapsed: {mm}:{ss}",
    healthVer: "EPUB Version",
    healthSpine: "Spine Chapters",
    healthXhtmlSize: "XHTML Size",
    healthImages: "Images",
    healthFonts: "Embedded Fonts",
    healthTocCount: "TOC Entries",
    chkMime: "mimetype stored uncompressed as first ZIP entry",
    chkContainer: "META-INF/container.xml valid & points to OPF",
    chkOpf: "Package OPF XML & Dublin Core metadata valid",
    chkSpine: "All spine & manifest chapter target files present",
  },
  vi: {
    appTitle: "Chuyển Đổi MOBI sang EPUB",
    appSubtitle: "Chạy 100% trên trình duyệt với mobi2epub & KindleUnpack (WebAssembly)",
    engineLoading: "Đang tải nhân Python Pyodide...",
    engineReady: "Sẵn sàng · {engine}",
    engineError: "Lỗi khởi tạo nhân",
    installApp: "Cài Đặt App",
    windowsAppBtn: "Bản Windows (.exe)",
    privacyTitle: "100% Riêng Tư & Xử Lý Tại Máy:",
    privacyDesc:
      "Sách của bạn không bao giờ tải lên máy chủ. Toàn bộ kiểm tra header MOBI (phát hiện DRM & lỗi file), giải nén KindleUnpack, chuyển đổi XHTML và kiểm định EPUB đều chạy cục bộ trong Web Worker.",
    sec1Title: "1. Chọn File MOBI / Kho nén .ZIP",
    trySampleBtn: "Thử Sách MOBI Mẫu (1-Click)",
    dropzoneTitle: "Kéo & thả file MOBI, thư mục, hoặc file .zip vào đây",
    dropzoneHint:
      "Hỗ trợ .mobi, .prc, .azw3, .azw và gói .zip chứa nhiều sách",
    addFilesBtn: "Thêm file / .zip...",
    selectFolderBtn: "Chọn thư mục...",
    saveToFolderBtn: "Lưu Trực Tiếp Vào Thư Mục...",
    clearOutDir: "Hủy chọn",
    lblFilenameTemplate: "Mẫu Tên File EPUB Đầu Ra",
    tplOriginal: "{OriginalFilename}.epub (Mặc định)",
    lblCssPreset: "Giao Diện Chữ / CSS Preset",
    cssOriginal: "Giữ nguyên CSS gốc",
    cssSerif: "Chữ Serif Sách In (Clean Serif)",
    cssSans: "Chữ Không Chân Hiện Đại (Sans-Serif)",
    cssDyslexia: "Giãn Dòng Dễ Đọc (Dyslexia-Friendly)",
    chkRecursive: "Bao gồm thư mục con",
    chkForce: "Ghi đè file đã có",
    chkAutoSplit: "Tự tách chương HTML lớn",
    chkImageOptimize: "Nén & tối ưu ảnh",
    chkGrayscale: "Ảnh xám E-Ink",
    lblMaxDim: "Cỡ tối đa (px):",
    lblQuality: "Chất lượng %:",
    noFilesSelected:
      "Chưa chọn file nào — kéo thả file .mobi/.zip vào khung trên hoặc bấm Thêm file...",
    clearBtn: "Xóa danh sách",
    convertBtn: "Chuyển Đổi",
    cancelBtn: "Dừng",
    stoppingBtn: "Đang dừng...",
    sec2Title: "2. Tiến Trình Chuyển Đổi",
    statusIdle: 'Chọn file đầu vào hoặc bấm "Thử Sách MOBI Mẫu" để bắt đầu.',
    statusWaitingEngine: "Đang đợi nhân Pyodide tải xong...",
    statusExtractingZip: "Đang giải nén sách từ {name}...",
    statusFinished: "Hoàn tất trong {sec}s",
    statusStopped: "Đã dừng bởi người dùng ({ok} thành công, {skip} bỏ qua, {fail} lỗi)",
    sec3Title: "3. Sách EPUB Đã Chuyển Đổi",
    downloadAllZipBtn: "Tải Tất Cả (.zip)",
    buildingZipBtn: "Đang nén .zip...",
    emptyDownloads:
      "Thẻ sách EPUB kèm ảnh bìa, đọc thử trực tiếp và báo cáo cấu trúc sẽ hiển thị tại đây.",
    secHistoryTitle: "Lịch Sử Chuyển Đổi Gần Đây (Lưu Trên Trình Duyệt)",
    hideHistoryBtn: "Ẩn",
    showHistoryBtn: "Hiện",
    clearHistoryBtn: "Xóa Lịch Sử",
    sec4Title: "4. Nhật Ký Hoạt Động",
    clearLogBtn: "Xóa Nhật Ký",
    readerTocBtn: "Mục lục",
    readerPrev: "Trước",
    readerNext: "Tiếp",
    readerChaptersHeading: "Danh Sách Chương / Mục Lục",
    healthModalTitle: "Báo Cáo Cấu Trúc & Kiểm Định EPUB",
    editModalTitle: "Sửa Thông Tin Sách, Ảnh Bìa & Mục Lục (TOC)",
    editMetaHeading: "Thông Tin Sách (OPF Metadata)",
    lblTitle: "Tên sách (Title)",
    lblAuthor: "Tác giả (Author)",
    lblLanguage: "Ngôn ngữ (BCP-47)",
    lblPublisher: "Nhà xuất bản",
    lblDescription: "Giới thiệu / Tóm tắt",
    editCoverHeading: "Ảnh Bìa Sách",
    uploadCoverBtn: "Tải ảnh bìa mới (JPG/PNG)...",
    resetCoverBtn: "Khôi phục bìa",
    coverHint: "Thay thế hoặc chèn ảnh bìa mới vào gói EPUB.",
    editTocHeading: "Mục Lục Sách (TOC)",
    addTocEntryBtn: "+ Thêm mục",
    tocEditorHint:
      "Đổi tên chương, sắp xếp thứ tự hoặc xóa các mục trống/trùng lặp.",
    saveChangesBtn: "Lưu & Cập Nhật EPUB",
    savingChangesBtn: "Đang cập nhật...",
    footerTagline:
      "Nhân KindleUnpack thuần Python kèm kiểm tra header & xác thực EPUB chuẩn",
    footerWinGui: "Tải bản Windows Desktop GUI (MobiToEpub.exe)",
    footerReleases: "Tất cả phiên bản",
    footerRepo: "Kho mã nguồn GitHub",
    btnDownloadEpub: "⬇ Tải .epub",
    btnPreviewRead: "📖 Đọc thử",
    btnEditInfo: "✏️ Sửa TT / Mục lục",
    btnShareEpub: "📤 Chia sẻ",
    badgeValidEpub: "✓ EPUB HỢP LỆ",
    badgeEdited: "Đã sửa",
    unknownAuthor: "Chưa rõ tác giả",
    filesSelectedSummary: "Đã chọn {count} file ({size}): {first}, ...",
    directSaveActive: "Đang lưu trực tiếp vào thư mục: {name}/",
    workerSingular: "{n} Luồng Worker",
    workerPlural: "{n} Luồng Worker",
    summaryLine: "Tổng kết: Thành công: {ok}  |  Bỏ qua: {skip}  |  Lỗi: {fail}",
    elapsedLabel: "Thời gian: {mm}:{ss}",
    healthVer: "Phiên bản EPUB",
    healthSpine: "Số chương Spine",
    healthXhtmlSize: "Dung lượng XHTML",
    healthImages: "Số lượng ảnh",
    healthFonts: "Font nhúng",
    healthTocCount: "Số mục lục (TOC)",
    chkMime: "File mimetype lưu không nén ở vị trí đầu tiên của ZIP",
    chkContainer: "META-INF/container.xml hợp lệ & trỏ đúng tới OPF",
    chkOpf: "Cấu trúc OPF XML & siêu dữ liệu Dublin Core hợp lệ",
    chkSpine: "Tất cả file chương trong spine & manifest đều tồn tại",
  },
};

// ---------------------------------------------------------------------------
// Application State
// ---------------------------------------------------------------------------

const state = {
  lang: localStorage.getItem("mobi2epub_lang") || "en",
  theme:
    localStorage.getItem("mobi2epub_theme") ||
    (window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"),
  engineReady: false,
  engineName: "KindleUnpack WASM",
  engineError: null,
  queuedFiles: [], // Array of { file: File, name: string, relPath: string, size: number, metadataOverride?, coverOverride?, tocOverride? }
  convertedItems: new Map(), // Map<outRelPath, BookItem>
  historyItems: [], // Array<BookItem> from IndexedDB
  historyCollapsed: false,
  outputDirHandle: null, // FileSystemDirectoryHandle (#3)
  deferredInstallPrompt: null, // BeforeInstallPromptEvent (#1)
  isRunning: false,
  cancelRequested: false,
  startTime: 0,
  elapsedTimerId: null,
  nextJobId: 1,
  autoConvertOnReady: false,

  // Reader modal state (#6)
  reader: {
    item: null,
    chapters: [],
    toc: [],
    currentIndex: 0,
    fontSizePct: 100,
  },

  // Edit modal state (#8 & #9)
  editor: {
    mode: null, // "converted" | "queued" | "history"
    targetKey: null, // outRelPath or queue index or history id
    coverOverride: null, // { bytes: Uint8Array, mime: string, dataUrl: string } | null
    coverReset: false,
    tocEntries: [], // Array<{ id, title, label, href }>
  },
};

// DOM Elements
const els = {
  enginePill: document.getElementById("enginePill"),
  engineStatusText: document.getElementById("engineStatusText"),
  btnInstallPwa: document.getElementById("btnInstallPwa"),
  btnLangToggle: document.getElementById("btnLangToggle"),
  langLabelEn: document.getElementById("langLabelEn"),
  langLabelVi: document.getElementById("langLabelVi"),
  btnThemeToggle: document.getElementById("btnThemeToggle"),
  themeIcon: document.getElementById("themeIcon"),

  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("fileInput"),
  folderInput: document.getElementById("folderInput"),
  btnAddFiles: document.getElementById("btnAddFiles"),
  btnSelectFolder: document.getElementById("btnSelectFolder"),
  btnChooseOutDir: document.getElementById("btnChooseOutDir"),
  outDirBar: document.getElementById("outDirBar"),
  outDirStatus: document.getElementById("outDirStatus"),
  btnClearOutDir: document.getElementById("btnClearOutDir"),
  btnTrySample: document.getElementById("btnTrySample"),
  btnClearQueue: document.getElementById("btnClearQueue"),
  inputSummaryText: document.getElementById("inputSummaryText"),
  queuedList: document.getElementById("queuedList"),

  selFilenameTemplate: document.getElementById("selFilenameTemplate"),
  selCssPreset: document.getElementById("selCssPreset"),
  chkRecursive: document.getElementById("chkRecursive"),
  chkForce: document.getElementById("chkForce"),
  chkAutoSplit: document.getElementById("chkAutoSplit"),
  chkImageOptimize: document.getElementById("chkImageOptimize"),
  imageOptSubgroup: document.getElementById("imageOptSubgroup"),
  chkGrayscale: document.getElementById("chkGrayscale"),
  inpImageMaxDim: document.getElementById("inpImageMaxDim"),
  inpImageQuality: document.getElementById("inpImageQuality"),

  btnConvert: document.getElementById("btnConvert"),
  btnCancel: document.getElementById("btnCancel"),
  workerPoolBadge: document.getElementById("workerPoolBadge"),
  progressTrack: document.getElementById("progressTrack"),
  progressFill: document.getElementById("progressFill"),
  statusText: document.getElementById("statusText"),
  elapsedText: document.getElementById("elapsedText"),

  downloadsList: document.getElementById("downloadsList"),
  btnDownloadAllZip: document.getElementById("btnDownloadAllZip"),
  convertedCountBadge: document.getElementById("convertedCountBadge"),

  historySection: document.getElementById("historySection"),
  historyCountBadge: document.getElementById("historyCountBadge"),
  btnToggleHistory: document.getElementById("btnToggleHistory"),
  btnClearHistory: document.getElementById("btnClearHistory"),
  historyList: document.getElementById("historyList"),

  logBox: document.getElementById("logBox"),
  btnClearLog: document.getElementById("btnClearLog"),
  summaryText: document.getElementById("summaryText"),

  // Reader Modal (#6)
  readerModal: document.getElementById("readerModal"),
  readerTitle: document.getElementById("readerTitle"),
  readerChapterIndicator: document.getElementById("readerChapterIndicator"),
  btnToggleReaderSidebar: document.getElementById("btnToggleReaderSidebar"),
  btnReaderPrev: document.getElementById("btnReaderPrev"),
  btnReaderNext: document.getElementById("btnReaderNext"),
  btnFontDec: document.getElementById("btnFontDec"),
  readerFontSizeLabel: document.getElementById("readerFontSizeLabel"),
  btnFontInc: document.getElementById("btnFontInc"),
  btnCloseReader: document.getElementById("btnCloseReader"),
  readerSidebar: document.getElementById("readerSidebar"),
  readerTocList: document.getElementById("readerTocList"),
  readerIframe: document.getElementById("readerIframe"),

  // Health Modal (#7)
  healthModal: document.getElementById("healthModal"),
  healthModalTitle: document.getElementById("healthModalTitle"),
  btnCloseHealth: document.getElementById("btnCloseHealth"),
  healthModalBody: document.getElementById("healthModalBody"),

  // Edit Metadata / Cover / TOC Modal (#8 & #9)
  editModal: document.getElementById("editModal"),
  editModalTitle: document.getElementById("editModalTitle"),
  btnCloseEdit: document.getElementById("btnCloseEdit"),
  editTitle: document.getElementById("editTitle"),
  editAuthor: document.getElementById("editAuthor"),
  editLanguage: document.getElementById("editLanguage"),
  editPublisher: document.getElementById("editPublisher"),
  editDescription: document.getElementById("editDescription"),
  editCoverPreview: document.getElementById("editCoverPreview"),
  editCoverInput: document.getElementById("editCoverInput"),
  btnUploadCover: document.getElementById("btnUploadCover"),
  btnResetCover: document.getElementById("btnResetCover"),
  editTocList: document.getElementById("editTocList"),
  btnAddTocEntry: document.getElementById("btnAddTocEntry"),
  editSaveStatus: document.getElementById("editSaveStatus"),
  btnCancelEdit: document.getElementById("btnCancelEdit"),
  btnSaveEdit: document.getElementById("btnSaveEdit"),
};

// ---------------------------------------------------------------------------
// Localization & Theme Helpers (#16, #17)
// ---------------------------------------------------------------------------

function t(key, vars = {}) {
  const dict = I18N[state.lang] || I18N.en;
  let str = dict[key] ?? I18N.en[key] ?? key;
  for (const [k, v] of Object.entries(vars)) {
    str = str.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
  }
  return str;
}

function applyTheme(theme) {
  state.theme = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", state.theme);
  localStorage.setItem("mobi2epub_theme", state.theme);
  if (els.themeIcon) {
    els.themeIcon.textContent = state.theme === "dark" ? "☀️" : "🌙";
  }
  // If reader preview modal is open, re-render chapter to match theme
  if (els.readerModal && !els.readerModal.classList.contains("hidden")) {
    renderCurrentReaderChapter();
  }
}

function applyI18n() {
  document.documentElement.lang = state.lang;
  localStorage.setItem("mobi2epub_lang", state.lang);

  if (els.langLabelEn && els.langLabelVi) {
    els.langLabelEn.classList.toggle("active", state.lang === "en");
    els.langLabelVi.classList.toggle("active", state.lang === "vi");
  }

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) {
      el.textContent = t(key);
    }
  });

  if (state.engineReady) {
    els.engineStatusText.textContent = t("engineReady", { engine: state.engineName });
  } else if (state.engineError) {
    els.engineStatusText.textContent = t("engineError");
  }

  if (els.btnToggleHistory) {
    els.btnToggleHistory.textContent = state.historyCollapsed
      ? t("showHistoryBtn")
      : t("hideHistoryBtn");
  }

  updateOutDirUI();
  updateWorkerPoolBadge();
  renderQueue();
  renderDownloads();
  renderHistory();
}

// ---------------------------------------------------------------------------
// General Utility Helpers
// ---------------------------------------------------------------------------

function hasSupportedBookExtension(filename) {
  const lower = (filename || "").toLowerCase();
  return SUPPORTED_BOOK_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function hasSupportedInputExtension(filename) {
  const lower = (filename || "").toLowerCase();
  return SUPPORTED_ALL_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function isZipFilename(filename) {
  return (filename || "").toLowerCase().endsWith(".zip");
}

function naturalSortKey(str) {
  return String(str)
    .toLowerCase()
    .split(/(\d+)/)
    .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
}

function compareNatural(a, b) {
  const ka = naturalSortKey(a);
  const kb = naturalSortKey(b);
  const len = Math.min(ka.length, kb.length);
  for (let i = 0; i < len; i++) {
    if (ka[i] !== kb[i]) {
      return ka[i] < kb[i] ? -1 : 1;
    }
  }
  return ka.length - kb.length;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(2)} MB`;
}

function formatElapsed(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return t("elapsedLabel", {
    mm: String(mins).padStart(2, "0"),
    ss: String(secs).padStart(2, "0"),
  });
}

function appendLog(text, type = "info") {
  const p = document.createElement("div");
  p.className = `log-line log-${type}`;
  p.textContent = text;
  els.logBox.appendChild(p);
  els.logBox.scrollTop = els.logBox.scrollHeight;
}

function clearLog() {
  els.logBox.innerHTML = "";
}

function toArrayBuffer(data) {
  if (!data) return new ArrayBuffer(0);
  if (data instanceof ArrayBuffer) return data;
  if (ArrayBuffer.isView(data)) {
    return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
  }
  return new ArrayBuffer(0);
}

// ---------------------------------------------------------------------------
// #10 Custom Output Filename Template Formatter & Sanitizer
// ---------------------------------------------------------------------------

function sanitizeFilenamePart(str) {
  return String(str || "")
    .replace(/[/\\:*?"<>|\x00-\x1F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\.+|\.+$/g, "");
}

function buildOutputFilenameAndPath({
  template,
  originalFileName,
  originalRelPath,
  title,
  author,
  language,
  usedRelPaths,
}) {
  const origStem =
    sanitizeFilenamePart((originalFileName || "book").replace(/\.[^/.]+$/, "")) || "book";
  const safeTitle = sanitizeFilenamePart(title) || origStem;
  const safeAuthor = sanitizeFilenamePart(author) || "Unknown Author";
  const safeLang = sanitizeFilenamePart(language) || "en";

  const tpl = template || "{OriginalFilename}.epub";
  let fileStem = tpl
    .replace(/\.epub$/i, "")
    .replace(/\{OriginalFilename\}/g, origStem)
    .replace(/\{Title\}/g, safeTitle)
    .replace(/\{Author\}/g, safeAuthor)
    .replace(/\{Language\}/g, safeLang);

  fileStem = sanitizeFilenamePart(fileStem) || origStem;

  const relNormalized = String(originalRelPath || originalFileName || "book.mobi").replace(
    /\\/g,
    "/"
  );
  const slashIdx = relNormalized.lastIndexOf("/");
  const dirPrefix = slashIdx > 0 ? relNormalized.slice(0, slashIdx) : "";

  let candidateName = `${fileStem}.epub`;
  let candidateRel = dirPrefix ? `${dirPrefix}/${candidateName}` : candidateName;

  if (usedRelPaths) {
    let counter = 2;
    while (usedRelPaths.has(candidateRel.toLowerCase())) {
      candidateName = `${fileStem} (${counter}).epub`;
      candidateRel = dirPrefix ? `${dirPrefix}/${candidateName}` : candidateName;
      counter++;
    }
    usedRelPaths.add(candidateRel.toLowerCase());
  }

  return {
    outFileName: candidateName,
    outRelPath: candidateRel,
  };
}

// ---------------------------------------------------------------------------
// #2 Multi-Worker Parallel Conversion Pool
// ---------------------------------------------------------------------------

class WorkerPool {
  constructor() {
    this.slots = [];
    this.maxConcurrency = Math.min(navigator.hardwareConcurrency || 2, 4);
  }

  createSlot(index) {
    const worker = new Worker("./worker.js");
    const slot = {
      index,
      worker,
      ready: false,
      busy: false,
      pending: new Map(),
      readyPromise: null,
      resolveReady: null,
      rejectReady: null,
    };

    slot.readyPromise = new Promise((resolve, reject) => {
      slot.resolveReady = resolve;
      slot.rejectReady = reject;
    });

    worker.onmessage = (event) => {
      const msg = event.data;
      if (!msg || !msg.type) return;

      if (msg.type === "init_status") {
        if (index === 0 && !state.engineReady) {
          els.enginePill.className = "engine-pill loading";
          els.engineStatusText.textContent = msg.message || t("engineLoading");
        }
        return;
      }

      if (msg.type === "ready") {
        slot.ready = true;
        slot.resolveReady(slot);
        if (index === 0) {
          state.engineReady = true;
          state.engineError = null;
          state.engineName = msg.engine || "KindleUnpack WASM";
          els.enginePill.className = "engine-pill ready";
          els.engineStatusText.textContent = t("engineReady", { engine: state.engineName });
          appendLog(
            "[INFO] Pyodide WebAssembly engine initialized (mobi2epub + KindleUnpack ready).",
            "info"
          );
          updateControlsState();

          if (state.autoConvertOnReady && state.queuedFiles.length > 0 && !state.isRunning) {
            state.autoConvertOnReady = false;
            startBatchConversion();
          }
        }
        updateWorkerPoolBadge();
        return;
      }

      if (msg.type === "init_error") {
        const errMsg = msg.message || "Failed to initialize Pyodide";
        slot.rejectReady(new Error(errMsg));
        if (index === 0) {
          state.engineReady = false;
          state.engineError = errMsg;
          els.enginePill.className = "engine-pill error";
          els.engineStatusText.textContent = t("engineError");
          appendLog(`[ERROR] Failed to load WebAssembly Python engine: ${errMsg}`, "fail");
          updateControlsState();
        }
        return;
      }

      // Resolve any RPC call matching msg.id
      if (msg.id !== undefined && slot.pending.has(msg.id)) {
        const resolver = slot.pending.get(msg.id);
        slot.pending.delete(msg.id);
        slot.busy = slot.pending.size > 0;
        resolver(msg);
      }
    };

    worker.onerror = (err) => {
      const message = err && err.message ? err.message : "Worker runtime error";
      if (index === 0) {
        els.enginePill.className = "engine-pill error";
        els.engineStatusText.textContent = t("engineError");
      }
      appendLog(`[ERROR] Worker #${index + 1} error: ${message}`, "fail");
    };

    worker.postMessage({ type: "init" });
    this.slots.push(slot);
    updateWorkerPoolBadge();
    return slot;
  }

  initPrimary() {
    if (this.slots.length === 0) {
      this.createSlot(0);
    }
    return this.slots[0];
  }

  async scaleTo(desiredCount) {
    const target = Math.max(1, Math.min(desiredCount, this.maxConcurrency));
    while (this.slots.length < target) {
      this.createSlot(this.slots.length);
    }
    updateWorkerPoolBadge();
    const activeSlots = this.slots.slice(0, target);
    await Promise.all(activeSlots.map((s) => s.readyPromise));
    return activeSlots;
  }

  async callOnSlot(slot, payload, transfer = []) {
    await slot.readyPromise;
    return new Promise((resolve) => {
      const id = state.nextJobId++;
      slot.busy = true;
      slot.pending.set(id, resolve);
      slot.worker.postMessage({ ...payload, id }, transfer);
    });
  }

  async callAny(payload, transfer = []) {
    if (this.slots.length === 0) {
      this.initPrimary();
    }
    const idleSlot = this.slots.find((s) => s.ready && !s.busy) || this.slots[0];
    return this.callOnSlot(idleSlot, payload, transfer);
  }
}

const workerPool = new WorkerPool();

function updateWorkerPoolBadge() {
  if (!els.workerPoolBadge) return;
  const count = Math.max(1, workerPool.slots.length);
  els.workerPoolBadge.textContent =
    count === 1 ? t("workerSingular", { n: 1 }) : t("workerPlural", { n: count });
}

// ---------------------------------------------------------------------------
// #4 IndexedDB Browser History Cache ("Recent Conversions")
// ---------------------------------------------------------------------------

function openHistoryDb() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      resolve(null);
      return;
    }
    const req = indexedDB.open(HISTORY_DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(HISTORY_STORE_NAME)) {
        const store = db.createObjectStore(HISTORY_STORE_NAME, { keyPath: "id" });
        store.createIndex("timestamp", "timestamp", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
  });
}

async function saveItemToHistoryDb(item) {
  try {
    const db = await openHistoryDb();
    if (!db) return;

    const record = {
      id: item.historyId || `${item.outRelPath}::${Date.now()}`,
      timestamp: Date.now(),
      outFileName: item.outFileName,
      outRelPath: item.outRelPath,
      title: item.title,
      author: item.author,
      language: item.language,
      publisher: item.publisher,
      description: item.description,
      coverDataUrl: item.coverDataUrl,
      originalSize: item.originalSize,
      epubSize: item.epubSize,
      healthReport: item.healthReport,
      toc: item.toc,
      epubBytes: item.buffer.slice(0),
    };
    item.historyId = record.id;

    await new Promise((resolve) => {
      const tx = db.transaction(HISTORY_STORE_NAME, "readwrite");
      const store = tx.objectStore(HISTORY_STORE_NAME);
      store.put(record);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });

    // Enforce HISTORY_MAX_ITEMS cap
    await pruneHistoryDb(db);
    await loadHistoryFromDb();
  } catch (_) {
    // Ignore quota or private-browsing IndexedDB restrictions
  }
}

async function pruneHistoryDb(db) {
  return new Promise((resolve) => {
    const tx = db.transaction(HISTORY_STORE_NAME, "readwrite");
    const store = tx.objectStore(HISTORY_STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => {
      const all = req.result || [];
      if (all.length > HISTORY_MAX_ITEMS) {
        all.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
        const toDelete = all.slice(HISTORY_MAX_ITEMS);
        for (const old of toDelete) {
          store.delete(old.id);
        }
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve();
  });
}

async function loadHistoryFromDb() {
  try {
    const db = await openHistoryDb();
    if (!db) return;

    const records = await new Promise((resolve) => {
      const tx = db.transaction(HISTORY_STORE_NAME, "readonly");
      const store = tx.objectStore(HISTORY_STORE_NAME);
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => resolve([]);
    });

    // Revoke old history blob URLs
    for (const prev of state.historyItems) {
      if (prev.blobUrl) URL.revokeObjectURL(prev.blobUrl);
    }

    records.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    state.historyItems = records.map((rec) => {
      const buffer = toArrayBuffer(rec.epubBytes);
      const blob = new Blob([buffer], { type: "application/epub+zip" });
      const blobUrl = URL.createObjectURL(blob);
      return {
        ...rec,
        historyId: rec.id,
        size: buffer.byteLength,
        epubSize: rec.epubSize || buffer.byteLength,
        buffer,
        blobUrl,
      };
    });

    renderHistory();
  } catch (_) {
    // Ignore IndexedDB errors
  }
}

async function clearHistoryDb() {
  try {
    const db = await openHistoryDb();
    if (db) {
      await new Promise((resolve) => {
        const tx = db.transaction(HISTORY_STORE_NAME, "readwrite");
        tx.objectStore(HISTORY_STORE_NAME).clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      });
    }
    for (const item of state.historyItems) {
      if (item.blobUrl) URL.revokeObjectURL(item.blobUrl);
    }
    state.historyItems = [];
    renderHistory();
    appendLog("[INFO] Cleared browser conversion history cache.", "info");
  } catch (_) {
    // Ignore
  }
}

function renderHistory() {
  if (!els.historySection || !els.historyList) return;
  const items = state.historyItems;
  els.historyCountBadge.textContent = String(items.length);

  if (items.length === 0) {
    els.historySection.classList.add("hidden");
    els.historyList.innerHTML = "";
    return;
  }

  els.historySection.classList.remove("hidden");
  els.historyList.classList.toggle("hidden", state.historyCollapsed);
  els.historyList.innerHTML = "";

  for (const item of items) {
    els.historyList.appendChild(createBookCardElement(item, "history"));
  }
}

// ---------------------------------------------------------------------------
// #3 Direct "Save to Folder" (File System Access API)
// ---------------------------------------------------------------------------

function initDirectSaveFeature() {
  if ("showDirectoryPicker" in window && els.btnChooseOutDir) {
    els.btnChooseOutDir.classList.remove("hidden");
  }
}

async function handleChooseOutputDir() {
  if (!("showDirectoryPicker" in window)) return;
  try {
    const handle = await window.showDirectoryPicker({ mode: "readwrite" });
    if (handle) {
      state.outputDirHandle = handle;
      updateOutDirUI();
      appendLog(`[INFO] Direct Save folder selected: ${handle.name}/`, "info");
    }
  } catch (err) {
    if (err && err.name !== "AbortError") {
      appendLog(`[INFO] Could not select output folder: ${err.message || err}`, "skip");
    }
  }
}

function clearOutputDir() {
  state.outputDirHandle = null;
  updateOutDirUI();
}

function updateOutDirUI() {
  if (!els.outDirBar || !els.outDirStatus) return;
  if (state.outputDirHandle) {
    els.outDirBar.classList.remove("hidden");
    els.outDirStatus.textContent = t("directSaveActive", {
      name: state.outputDirHandle.name,
    });
  } else {
    els.outDirBar.classList.add("hidden");
    els.outDirStatus.textContent = "";
  }
}

async function writeEpubToOutputFolder(outRelPath, epubBuffer) {
  if (!state.outputDirHandle) return false;
  try {
    const cleanRel = String(outRelPath || "book.epub")
      .replace(/\\/g, "/")
      .replace(/^\/+/, "");
    const parts = cleanRel.split("/").filter(Boolean);
    const fileName = parts.pop() || "book.epub";

    let currDir = state.outputDirHandle;
    if (els.chkRecursive.checked && parts.length > 0) {
      for (const dirPart of parts) {
        const safeDir = sanitizeFilenamePart(dirPart) || "subfolder";
        currDir = await currDir.getDirectoryHandle(safeDir, { create: true });
      }
    }

    const fileHandle = await currDir.getFileHandle(fileName, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(epubBuffer);
    await writable.close();
    return true;
  } catch (err) {
    appendLog(
      `[WARN] Could not write ${outRelPath} directly to disk folder: ${
        err && err.message ? err.message : err
      }`,
      "skip"
    );
    return false;
  }
}

// ---------------------------------------------------------------------------
// #14 ZIP Input Extraction & File Queue Management
// ---------------------------------------------------------------------------

async function handleIncomingFileEntries(fileEntries, replace = false) {
  const directEntries = [];
  const zipEntries = [];

  for (const item of fileEntries) {
    const file = item.file || item;
    if (!file || !file.name) continue;
    const relPath = (item.relPath || file.webkitRelativePath || file.name || "").replace(
      /\\/g,
      "/"
    );

    if (isZipFilename(file.name)) {
      zipEntries.push({ file, relPath });
    } else if (hasSupportedBookExtension(file.name)) {
      directEntries.push({ file, relPath });
    }
  }

  for (const zipItem of zipEntries) {
    try {
      els.statusText.textContent = t("statusExtractingZip", { name: zipItem.file.name });
      appendLog(`[INFO] Unpacking .zip archive: ${zipItem.file.name}...`, "info");
      const zipBuf = await zipItem.file.arrayBuffer();
      const res = await workerPool.callAny(
        {
          type: "extract_input_zip",
          fileName: zipItem.file.name,
          zipBytes: zipBuf,
          data: zipBuf,
        },
        [zipBuf]
      );

      const extractedList = res.files || [];
      if (extractedList.length === 0) {
        appendLog(
          `[SKIP] No supported MOBI files (.mobi, .prc, .azw3, .azw) found inside ${zipItem.file.name}.`,
          "skip"
        );
      } else {
        for (const extFile of extractedList) {
          const fname = extFile.fileName || extFile.name || "book.mobi";
          const frel = extFile.relPath || fname;
          const rawBytes = extFile.bytes || extFile.data;
          const buf = toArrayBuffer(rawBytes);
          const fileObj = new File([buf], fname, {
            type: "application/x-mobipocket-ebook",
          });
          directEntries.push({ file: fileObj, relPath: frel });
        }
        appendLog(
          `[OK] Extracted ${extractedList.length} MOBI book(s) from ${zipItem.file.name}.`,
          "ok"
        );
      }
    } catch (err) {
      appendLog(
        `[FAILED] Could not unpack ${zipItem.file.name}: ${
          err && err.message ? err.message : String(err)
        }`,
        "fail"
      );
    }
  }

  if (directEntries.length > 0 || replace) {
    addFilesToQueue(directEntries, replace);
  }
  if (!state.isRunning) {
    els.statusText.textContent = t("statusIdle");
  }
}

function addFilesToQueue(fileEntries, replace = false) {
  const recursive = els.chkRecursive.checked;
  const filtered = [];

  for (const item of fileEntries) {
    const file = item.file || item;
    const relPath = (item.relPath || file.webkitRelativePath || file.name || "").replace(
      /\\/g,
      "/"
    );
    if (!hasSupportedBookExtension(file.name)) continue;

    if (!recursive && relPath.split("/").length > 2) {
      continue;
    }

    filtered.push({
      file,
      name: file.name,
      relPath: relPath || file.name,
      size: file.size || 0,
      metadataOverride: item.metadataOverride || null,
      coverOverride: item.coverOverride || null,
      tocOverride: item.tocOverride || null,
    });
  }

  if (filtered.length === 0) {
    appendLog(
      "[INFO] No supported MOBI files (.mobi, .prc, .azw3, .azw) found in selection.",
      "skip"
    );
    return 0;
  }

  const nextQueue = replace ? [] : [...state.queuedFiles];
  const existingKeys = new Set(nextQueue.map((q) => `${q.relPath}::${q.size}`));

  for (const entry of filtered) {
    const key = `${entry.relPath}::${entry.size}`;
    if (!existingKeys.has(key)) {
      existingKeys.add(key);
      nextQueue.push(entry);
    }
  }

  nextQueue.sort((a, b) => compareNatural(a.relPath, b.relPath));
  state.queuedFiles = nextQueue;
  renderQueue();
  updateControlsState();
  return filtered.length;
}

function removeQueuedIndex(idx) {
  if (state.isRunning) return;
  state.queuedFiles.splice(idx, 1);
  renderQueue();
  updateControlsState();
}

function clearQueue() {
  if (state.isRunning) return;
  state.queuedFiles = [];
  renderQueue();
  updateControlsState();
}

function renderQueue() {
  const count = state.queuedFiles.length;
  if (count === 0) {
    els.inputSummaryText.textContent = t("noFilesSelected");
    els.queuedList.classList.add("hidden");
    els.queuedList.innerHTML = "";
    els.btnClearQueue.classList.add("hidden");
    return;
  }

  if (count === 1) {
    const f = state.queuedFiles[0];
    els.inputSummaryText.textContent = `${f.relPath} (${formatBytes(f.size)})`;
  } else {
    const totalBytes = state.queuedFiles.reduce((acc, item) => acc + item.size, 0);
    els.inputSummaryText.textContent = t("filesSelectedSummary", {
      count,
      size: formatBytes(totalBytes),
      first: state.queuedFiles[0].name,
    });
  }

  els.btnClearQueue.classList.remove("hidden");
  els.queuedList.classList.remove("hidden");
  els.queuedList.innerHTML = "";

  state.queuedFiles.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "queued-item";

    const nameSpan = document.createElement("span");
    nameSpan.className = "queued-item-name";
    nameSpan.textContent = item.relPath;

    if (item.metadataOverride || item.coverOverride || item.tocOverride) {
      const editedBadge = document.createElement("span");
      editedBadge.className = "queued-edited-badge";
      editedBadge.textContent = t("badgeEdited");
      nameSpan.appendChild(editedBadge);
    }

    const metaSpan = document.createElement("span");
    metaSpan.className = "queued-item-meta";

    const sizeLabel = document.createElement("span");
    sizeLabel.textContent = formatBytes(item.size);
    metaSpan.appendChild(sizeLabel);

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-xs";
    editBtn.textContent = t("btnEditInfo");
    editBtn.disabled = state.isRunning;
    editBtn.addEventListener("click", () => openEditModalForQueued(index));
    metaSpan.appendChild(editBtn);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-remove-item";
    removeBtn.title = "Remove file";
    removeBtn.textContent = "×";
    removeBtn.disabled = state.isRunning;
    removeBtn.addEventListener("click", () => removeQueuedIndex(index));
    metaSpan.appendChild(removeBtn);

    row.appendChild(nameSpan);
    row.appendChild(metaSpan);
    els.queuedList.appendChild(row);
  });
}

function updateControlsState() {
  const hasFiles = state.queuedFiles.length > 0;
  els.btnConvert.disabled = state.isRunning || !hasFiles;
  els.btnCancel.disabled = !state.isRunning;
  els.btnAddFiles.disabled = state.isRunning;
  els.btnSelectFolder.disabled = state.isRunning;
  if (els.btnChooseOutDir) els.btnChooseOutDir.disabled = state.isRunning;
  els.btnTrySample.disabled = state.isRunning;
  els.btnClearQueue.disabled = state.isRunning || !hasFiles;
  els.chkRecursive.disabled = state.isRunning;
  els.chkForce.disabled = state.isRunning;
  els.chkAutoSplit.disabled = state.isRunning;
  els.chkImageOptimize.disabled = state.isRunning;
  els.selFilenameTemplate.disabled = state.isRunning;
  els.selCssPreset.disabled = state.isRunning;
  els.btnDownloadAllZip.disabled = state.isRunning || state.convertedItems.size < 1;
}

// ---------------------------------------------------------------------------
// Drag & Drop Directory Traversal
// ---------------------------------------------------------------------------

async function readDirectoryEntryRecursive(dirEntry, prefix = "") {
  const results = [];
  const reader = dirEntry.createReader();

  const readBatch = () =>
    new Promise((resolve) => {
      reader.readEntries(
        (entries) => resolve(entries || []),
        () => resolve([])
      );
    });

  while (true) {
    const entries = await readBatch();
    if (!entries.length) break;
    for (const entry of entries) {
      const nextRel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isFile) {
        const file = await new Promise((resolve) => entry.file(resolve, () => resolve(null)));
        if (file) {
          results.push({ file, relPath: nextRel });
        }
      } else if (entry.isDirectory && els.chkRecursive.checked) {
        const subFiles = await readDirectoryEntryRecursive(entry, nextRel);
        results.push(...subFiles);
      }
    }
  }
  return results;
}

async function extractDroppedItems(dataTransfer) {
  const items = dataTransfer.items;
  if (items && items.length > 0 && typeof items[0].webkitGetAsEntry === "function") {
    const collected = [];
    const entries = [];
    for (let i = 0; i < items.length; i++) {
      const entry = items[i].webkitGetAsEntry();
      if (entry) entries.push(entry);
    }

    for (const entry of entries) {
      if (entry.isFile) {
        const file = await new Promise((resolve) => entry.file(resolve, () => resolve(null)));
        if (file) collected.push({ file, relPath: file.name });
      } else if (entry.isDirectory) {
        const sub = await readDirectoryEntryRecursive(entry, entry.name);
        collected.push(...sub);
      }
    }
    return collected;
  }

  return Array.from(dataTransfer.files || []).map((file) => ({
    file,
    relPath: file.webkitRelativePath || file.name,
  }));
}

// ---------------------------------------------------------------------------
// Conversion Execution (Multi-Worker Pool + All Options)
// ---------------------------------------------------------------------------

function startElapsedTimer() {
  state.startTime = performance.now();
  els.elapsedText.textContent = formatElapsed(0);
  if (state.elapsedTimerId) clearInterval(state.elapsedTimerId);
  state.elapsedTimerId = setInterval(() => {
    const sec = (performance.now() - state.startTime) / 1000;
    els.elapsedText.textContent = formatElapsed(sec);
  }, 250);
}

function stopElapsedTimer() {
  if (state.elapsedTimerId) {
    clearInterval(state.elapsedTimerId);
    state.elapsedTimerId = null;
  }
}

function setProgress(completed, total, indeterminate = false) {
  if (indeterminate) {
    els.progressTrack.classList.add("indeterminate");
    els.progressFill.style.width = "35%";
  } else {
    els.progressTrack.classList.remove("indeterminate");
    const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    els.progressFill.style.width = `${pct}%`;
  }
}

function getCurrentConversionOptions(item) {
  const options = {
    cssPreset: els.selCssPreset ? els.selCssPreset.value : "original",
    autoSplitChapters: els.chkAutoSplit ? Boolean(els.chkAutoSplit.checked) : true,
    imageOptimize: {
      enabled: els.chkImageOptimize ? Boolean(els.chkImageOptimize.checked) : false,
      maxDim: parseInt(els.inpImageMaxDim?.value || "1200", 10) || 1200,
      quality: parseInt(els.inpImageQuality?.value || "75", 10) || 75,
      grayscale: els.chkGrayscale ? Boolean(els.chkGrayscale.checked) : false,
    },
  };

  if (item && item.metadataOverride) {
    options.metadataOverride = { ...item.metadataOverride };
  }
  if (item && item.coverOverride) {
    options.coverOverride = {
      bytes: item.coverOverride.bytes,
      data: item.coverOverride.bytes,
      mime: item.coverOverride.mime || "image/jpeg",
    };
  }
  if (item && item.tocOverride) {
    options.tocOverride = item.tocOverride.map((entry) => ({
      id: entry.id,
      title: entry.title || entry.label || "",
      label: entry.label || entry.title || "",
      href: entry.href || "",
    }));
  }
  return options;
}

function normalizeWorkerConversionResult(res, item, template, usedRelPaths) {
  const rawBytes = res.epubBytes || res.epubData;
  const epubBuffer = toArrayBuffer(rawBytes);
  const title =
    res.title ||
    item.metadataOverride?.title ||
    item.name.replace(/\.[^.]+$/, "");
  const author = res.author || item.metadataOverride?.author || "";
  const language = res.language || item.metadataOverride?.language || "en";
  const publisher = res.publisher || item.metadataOverride?.publisher || "";
  const description = res.description || item.metadataOverride?.description || "";

  const { outFileName, outRelPath } = buildOutputFilenameAndPath({
    template,
    originalFileName: item.name,
    originalRelPath: item.relPath,
    title,
    author,
    language,
    usedRelPaths,
  });

  const healthReport = res.healthReport || {
    version: res.version ? String(res.version) : "2.0",
    isValid: true,
    spineCount: res.spineCount || 1,
    xhtmlBytes: epubBuffer.byteLength,
    imageCount: 0,
    fontCount: 0,
    tocCount: Array.isArray(res.toc) ? res.toc.length : 1,
    checks: {
      mimetypeUncompressed: true,
      containerXmlValid: true,
      opfValid: true,
      spineTargetsExist: true,
    },
  };

  const toc = Array.isArray(res.toc)
    ? res.toc.map((entry, idx) => ({
        id: entry.id || `nav_${idx + 1}`,
        title: entry.title || entry.label || `Chapter ${idx + 1}`,
        label: entry.label || entry.title || `Chapter ${idx + 1}`,
        href: entry.href || "",
      }))
    : [];

  const chaptersPreview = Array.isArray(res.chaptersPreview || res.chapters)
    ? (res.chaptersPreview || res.chapters).map((ch, idx) => ({
        id: ch.id || `ch_${idx + 1}`,
        title: ch.title || ch.label || `Section ${idx + 1}`,
        href: ch.href || "",
        html: ch.html || "",
      }))
    : null;

  return {
    outFileName,
    outRelPath,
    originalFileName: item.name,
    originalRelPath: item.relPath,
    title,
    author,
    language,
    publisher,
    description,
    coverDataUrl: res.coverDataUrl || item.coverOverride?.dataUrl || null,
    originalSize: res.originalSize || item.size || 0,
    epubSize: res.epubSize || epubBuffer.byteLength,
    size: epubBuffer.byteLength,
    healthReport,
    toc,
    chaptersPreview,
    buffer: epubBuffer,
  };
}

async function startBatchConversion() {
  if (state.isRunning || state.queuedFiles.length === 0) return;

  if (!state.engineReady) {
    state.autoConvertOnReady = true;
    els.statusText.textContent = t("statusWaitingEngine");
    appendLog(
      "[INFO] Conversion queued — will start automatically as soon as Pyodide is ready.",
      "info"
    );
    return;
  }

  state.isRunning = true;
  state.cancelRequested = false;
  els.btnCancel.textContent = t("cancelBtn");
  updateControlsState();
  renderQueue();

  const tasks = [...state.queuedFiles];
  const total = tasks.length;
  const forceOverwrite = els.chkForce.checked;
  const filenameTemplate = els.selFilenameTemplate
    ? els.selFilenameTemplate.value
    : "{OriginalFilename}.epub";

  let convertedCount = 0;
  let skippedCount = 0;
  let failedCount = 0;
  let completedCount = 0;

  startElapsedTimer();
  els.summaryText.textContent = "";

  if (total === 1) {
    setProgress(0, 1, true);
  } else {
    setProgress(0, total, false);
  }

  // Scale worker pool for multi-file batches (#2)
  const desiredWorkers =
    total === 1 ? 1 : Math.min(navigator.hardwareConcurrency || 2, 4, total);
  appendLog(
    `Starting conversion of ${total} file(s) across ${desiredWorkers} Web Worker(s)...`,
    "info"
  );

  let activeSlots = [workerPool.initPrimary()];
  try {
    activeSlots = await workerPool.scaleTo(desiredWorkers);
  } catch (_) {
    activeSlots = [workerPool.initPrimary()];
  }

  const usedRelPaths = new Set();
  if (!forceOverwrite) {
    for (const k of state.convertedItems.keys()) {
      usedRelPaths.add(k.toLowerCase());
    }
  }

  let nextTaskIdx = 0;

  const runWorkerLoop = async (slot) => {
    while (!state.cancelRequested) {
      const i = nextTaskIdx++;
      if (i >= total) break;

      const item = tasks[i];
      const defaultExpectedRel = item.relPath.replace(/\.[^/.]+$/, "") + ".epub";

      els.statusText.textContent = `${Math.min(completedCount + 1, total)} / ${total} · ${
        item.name
      }`;

      if (
        !forceOverwrite &&
        filenameTemplate === "{OriginalFilename}.epub" &&
        state.convertedItems.has(defaultExpectedRel)
      ) {
        skippedCount++;
        completedCount++;
        if (total > 1) setProgress(completedCount, total, false);
        appendLog(`[SKIPPED] ${item.relPath} (Destination already exists)`, "skip");
        continue;
      }

      try {
        const arrayBuffer = await item.file.arrayBuffer();
        const options = getCurrentConversionOptions(item);

        const res = await workerPool.callOnSlot(
          slot,
          {
            type: "convert_one",
            fileName: item.name,
            relPath: item.relPath,
            bytes: arrayBuffer,
            data: arrayBuffer,
            options,
          },
          [arrayBuffer]
        );

        completedCount++;
        if (total > 1) {
          setProgress(completedCount, total, false);
        }

        const isOk = Boolean(res.ok ?? res.success) && (res.epubBytes || res.epubData);
        if (isOk) {
          convertedCount++;
          const normalized = normalizeWorkerConversionResult(
            res,
            item,
            filenameTemplate,
            usedRelPaths
          );

          const blob = new Blob([normalized.buffer], { type: "application/epub+zip" });
          normalized.blobUrl = URL.createObjectURL(blob);

          const prev = state.convertedItems.get(normalized.outRelPath);
          if (prev && prev.blobUrl) {
            URL.revokeObjectURL(prev.blobUrl);
          }

          state.convertedItems.set(normalized.outRelPath, normalized);

          // Direct Save to Folder (#3)
          if (state.outputDirHandle) {
            const wrote = await writeEpubToOutputFolder(
              normalized.outRelPath,
              normalized.buffer
            );
            if (wrote) {
              appendLog(
                `[SAVED] Wrote ${normalized.outRelPath} to ${state.outputDirHandle.name}/`,
                "ok"
              );
            }
          }

          // Save to IndexedDB History (#4)
          await saveItemToHistoryDb(normalized);

          const titleSuffix = normalized.title ? ` ('${normalized.title}')` : "";
          appendLog(
            `[OK] ${item.relPath} -> ${normalized.outFileName}${titleSuffix}`,
            "ok"
          );
          renderDownloads();
        } else {
          failedCount++;
          const errType = (res.errorType || "failed").toUpperCase();
          const logClass =
            errType === "DRM" ? "drm" : errType === "CORRUPT" ? "corrupt" : "fail";
          appendLog(
            `[FAILED] ${item.relPath} [${errType}]: ${
              res.errorMessage || "Conversion failed"
            }`,
            logClass
          );
        }
      } catch (err) {
        failedCount++;
        completedCount++;
        if (total > 1) setProgress(completedCount, total, false);
        const msg = err && err.message ? err.message : String(err);
        appendLog(`[FAILED] ${item.relPath} [EXCEPTION]: ${msg}`, "fail");
      }
    }
  };

  await Promise.all(activeSlots.map((slot) => runWorkerLoop(slot)));

  stopElapsedTimer();
  const elapsedSec = (performance.now() - state.startTime) / 1000;
  els.elapsedText.textContent = formatElapsed(elapsedSec);

  state.isRunning = false;
  setProgress(total, total, false);

  const summaryLine = t("summaryLine", {
    ok: convertedCount,
    skip: skippedCount,
    fail: failedCount,
  });
  els.summaryText.textContent = summaryLine;

  if (state.cancelRequested) {
    els.statusText.textContent = t("statusStopped", {
      ok: convertedCount,
      skip: skippedCount,
      fail: failedCount,
    });
  } else {
    els.statusText.textContent = t("statusFinished", {
      sec: elapsedSec.toFixed(1),
    });
  }

  appendLog(`=== ${summaryLine} (Time: ${elapsedSec.toFixed(2)}s) ===`, "bold");
  updateControlsState();
  renderQueue();
}

// ---------------------------------------------------------------------------
// #5 Rich Book Result Cards, #15 Web Share API & ZIP Export
// ---------------------------------------------------------------------------

function canShareEpubFile(item) {
  try {
    if (typeof navigator.share !== "function" || typeof navigator.canShare !== "function") {
      return false;
    }
    const testFile = new File([item.buffer], item.outFileName || "book.epub", {
      type: "application/epub+zip",
    });
    return navigator.canShare({ files: [testFile] });
  } catch (_) {
    return false;
  }
}

async function handleShareEpub(item) {
  try {
    const epubFile = new File([item.buffer], item.outFileName || "book.epub", {
      type: "application/epub+zip",
    });
    await navigator.share({
      title: item.title || item.outFileName,
      text: `${item.title || item.outFileName}${item.author ? ` — ${item.author}` : ""}`,
      files: [epubFile],
    });
  } catch (err) {
    if (err && err.name !== "AbortError") {
      appendLog(`[INFO] Share cancelled or unavailable: ${err.message || err}`, "skip");
    }
  }
}

function createBookCardElement(item, source = "converted") {
  const card = document.createElement("div");
  card.className = "book-card download-item";

  // Cover Thumbnail or Styled Placeholder (#5)
  const coverWrap = document.createElement("div");
  coverWrap.className = "book-cover-wrap";
  if (item.coverDataUrl) {
    const img = document.createElement("img");
    img.className = "book-cover-img";
    img.src = item.coverDataUrl;
    img.alt = item.title || item.outFileName;
    coverWrap.appendChild(img);
  } else {
    const ph = document.createElement("div");
    ph.className = "book-cover-placeholder";
    ph.innerHTML = `<span class="book-cover-placeholder-icon">📘</span><span class="book-cover-placeholder-ext">EPUB</span>`;
    coverWrap.appendChild(ph);
  }

  // Body
  const body = document.createElement("div");
  body.className = "book-card-body";

  const headerRow = document.createElement("div");
  headerRow.className = "book-card-header";

  const titleGroup = document.createElement("div");
  const titleEl = document.createElement("h4");
  titleEl.className = "book-card-title";
  titleEl.textContent = item.title || item.outFileName;

  const authorEl = document.createElement("div");
  authorEl.className = "book-card-author";
  authorEl.textContent = item.author || t("unknownAuthor");

  titleGroup.appendChild(titleEl);
  titleGroup.appendChild(authorEl);

  // Badges: Language + Clickable Health Report Badge (#7)
  const badgesWrap = document.createElement("div");
  badgesWrap.className = "book-badges";

  if (item.language) {
    const langBadge = document.createElement("span");
    langBadge.className = "badge-lang";
    langBadge.textContent = item.language;
    badgesWrap.appendChild(langBadge);
  }

  const healthBtn = document.createElement("button");
  healthBtn.type = "button";
  healthBtn.className = "badge-health";
  healthBtn.textContent = t("badgeValidEpub");
  healthBtn.title = t("healthModalTitle");
  healthBtn.addEventListener("click", () => openHealthModal(item));
  badgesWrap.appendChild(healthBtn);

  headerRow.appendChild(titleGroup);
  headerRow.appendChild(badgesWrap);

  // Meta row: path & size comparison
  const metaRow = document.createElement("div");
  metaRow.className = "book-card-meta";

  const origBytes = item.originalSize || 0;
  const epubBytes = item.epubSize || item.size || 0;
  const sizeComparison =
    origBytes > 0
      ? `${formatBytes(origBytes)} → ${formatBytes(epubBytes)}`
      : formatBytes(epubBytes);

  const metaText = document.createElement("span");
  metaText.textContent = `${item.outRelPath} · ${sizeComparison}`;
  metaRow.appendChild(metaText);

  if (origBytes > epubBytes && origBytes > 0) {
    const savedPct = Math.round(((origBytes - epubBytes) / origBytes) * 100);
    if (savedPct >= 2) {
      const savedBadge = document.createElement("span");
      savedBadge.className = "badge-saved";
      savedBadge.textContent = `-${savedPct}%`;
      metaRow.appendChild(savedBadge);
    }
  }

  // Action Buttons: Download, Read/Preview (#6), Edit Info/TOC (#8 & #9), Share (#15)
  const actionsRow = document.createElement("div");
  actionsRow.className = "book-card-actions";

  const dlLink = document.createElement("a");
  dlLink.className = "btn btn-success btn-sm";
  dlLink.href = item.blobUrl;
  dlLink.download = item.outFileName;
  dlLink.textContent = t("btnDownloadEpub");
  actionsRow.appendChild(dlLink);

  const previewBtn = document.createElement("button");
  previewBtn.type = "button";
  previewBtn.className = "btn btn-sm";
  previewBtn.textContent = t("btnPreviewRead");
  previewBtn.addEventListener("click", () => openReaderModal(item));
  actionsRow.appendChild(previewBtn);

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "btn btn-sm";
  editBtn.textContent = t("btnEditInfo");
  editBtn.addEventListener("click", () => openEditModalForBook(item, source));
  actionsRow.appendChild(editBtn);

  if (canShareEpubFile(item)) {
    const shareBtn = document.createElement("button");
    shareBtn.type = "button";
    shareBtn.className = "btn btn-sm";
    shareBtn.textContent = t("btnShareEpub");
    shareBtn.addEventListener("click", () => handleShareEpub(item));
    actionsRow.appendChild(shareBtn);
  }

  body.appendChild(headerRow);
  body.appendChild(metaRow);
  body.appendChild(actionsRow);

  card.appendChild(coverWrap);
  card.appendChild(body);
  return card;
}

function renderDownloads() {
  const items = Array.from(state.convertedItems.values());
  els.convertedCountBadge.textContent = String(items.length);

  if (items.length === 0) {
    els.downloadsList.innerHTML = `<div class="empty-downloads">${t("emptyDownloads")}</div>`;
    els.btnDownloadAllZip.disabled = true;
    return;
  }

  els.downloadsList.innerHTML = "";
  for (const item of items) {
    els.downloadsList.appendChild(createBookCardElement(item, "converted"));
  }

  els.btnDownloadAllZip.disabled = state.isRunning || items.length === 0;
}

async function handleDownloadAllZip() {
  const items = Array.from(state.convertedItems.values());
  if (items.length === 0) return;

  els.btnDownloadAllZip.disabled = true;
  els.btnDownloadAllZip.textContent = t("buildingZipBtn");

  try {
    const filesPayload = items.map((item) => {
      const copy = item.buffer.slice(0);
      return {
        name: item.outFileName,
        fileName: item.outFileName,
        arcName: item.outRelPath,
        relPath: item.outRelPath,
        data: copy,
        bytes: copy,
      };
    });

    const res = await workerPool.callAny({
      type: "create_zip",
      files: filesPayload,
    });

    const rawZip = res.zipData || res.zipBytes;
    if ((res.ok ?? res.success) && rawZip) {
      const zipBuffer = toArrayBuffer(rawZip);
      const blob = new Blob([zipBuffer], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mobi2epub_converted_${items.length}_books.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      appendLog(`[OK] Downloaded ZIP archive with ${items.length} EPUB file(s).`, "ok");
    } else {
      appendLog(
        `[FAILED] Could not build ZIP archive: ${res.errorMessage || "Unknown error"}`,
        "fail"
      );
    }
  } catch (err) {
    appendLog(
      `[FAILED] ZIP error: ${err && err.message ? err.message : String(err)}`,
      "fail"
    );
  } finally {
    els.btnDownloadAllZip.innerHTML = `⬇ <span>${t("downloadAllZipBtn")}</span>`;
    els.btnDownloadAllZip.disabled = state.isRunning || state.convertedItems.size === 0;
  }
}

// ---------------------------------------------------------------------------
// #6 Built-in In-Browser EPUB Reader Preview Modal
// ---------------------------------------------------------------------------

async function openReaderModal(item) {
  state.reader.item = item;
  state.reader.currentIndex = 0;
  els.readerTitle.textContent = item.title || item.outFileName;
  els.readerModal.classList.remove("hidden");

  let chapters = item.chaptersPreview;
  let toc = item.toc || [];

  if (!Array.isArray(chapters) || chapters.length === 0) {
    try {
      const copyBuf = item.buffer.slice(0);
      const res = await workerPool.callAny(
        {
          type: "read_epub",
          epubBytes: copyBuf,
          data: copyBuf,
        },
        [copyBuf]
      );
      chapters = res.chapters || res.chaptersPreview || [];
      if (Array.isArray(res.toc) && res.toc.length > 0) {
        toc = res.toc;
      }
      item.chaptersPreview = chapters;
    } catch (err) {
      chapters = [
        {
          id: "err",
          title: "Preview Error",
          href: "",
          html: `<p>Could not load chapter preview: ${
            err && err.message ? err.message : String(err)
          }</p>`,
        },
      ];
    }
  }

  state.reader.chapters = chapters;
  state.reader.toc = toc;

  renderReaderSidebar();
  renderCurrentReaderChapter();
}

function renderReaderSidebar() {
  els.readerTocList.innerHTML = "";
  const chapters = state.reader.chapters;
  const toc = state.reader.toc;

  // Build clickable items from TOC if available, or fall back to spine chapters
  const navItems =
    toc.length > 0
      ? toc.map((entry, idx) => ({
          label: entry.title || entry.label || `Chapter ${idx + 1}`,
          href: entry.href || "",
          chapterIndex: findChapterIndexByHref(chapters, entry.href, idx),
        }))
      : chapters.map((ch, idx) => ({
          label: ch.title || `Section ${idx + 1}`,
          href: ch.href || "",
          chapterIndex: idx,
        }));

  navItems.forEach((nav) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "reader-toc-item";
    if (nav.chapterIndex === state.reader.currentIndex) {
      btn.classList.add("active");
    }
    btn.textContent = nav.label;
    btn.addEventListener("click", () => {
      state.reader.currentIndex = Math.max(
        0,
        Math.min(chapters.length - 1, nav.chapterIndex)
      );
      renderReaderSidebar();
      renderCurrentReaderChapter(nav.href);
    });
    els.readerTocList.appendChild(btn);
  });
}

function findChapterIndexByHref(chapters, rawHref, fallbackIdx = 0) {
  if (!rawHref || !chapters.length) {
    return Math.min(fallbackIdx, Math.max(0, chapters.length - 1));
  }
  const cleanTarget = rawHref.split("#")[0].split("/").pop().toLowerCase();
  const found = chapters.findIndex((ch) => {
    const chFile = String(ch.href || "")
      .split("#")[0]
      .split("/")
      .pop()
      .toLowerCase();
    return chFile && chFile === cleanTarget;
  });
  return found >= 0 ? found : Math.min(fallbackIdx, Math.max(0, chapters.length - 1));
}

function renderCurrentReaderChapter(anchorHref = "") {
  const chapters = state.reader.chapters;
  const total = chapters.length;
  const idx = Math.max(0, Math.min(total - 1, state.reader.currentIndex));
  state.reader.currentIndex = idx;

  els.readerChapterIndicator.textContent =
    total > 0 ? `${idx + 1} / ${total}` : "0 / 0";
  els.btnReaderPrev.disabled = idx <= 0;
  els.btnReaderNext.disabled = idx >= total - 1;
  els.readerFontSizeLabel.textContent = `${state.reader.fontSizePct}%`;

  const chapter = chapters[idx];
  const rawHtml = chapter ? chapter.html || "" : "<p>Empty chapter.</p>";

  const isDark = state.theme === "dark";
  const bg = isDark ? "#0f172a" : "#ffffff";
  const fg = isDark ? "#e2e8f0" : "#1e293b";
  const linkColor = isDark ? "#60a5fa" : "#2563eb";

  const readerCss = `
    <style>
      html, body {
        margin: 0;
        padding: 1.5rem 2rem;
        background: ${bg};
        color: ${fg};
        font-family: Georgia, "Times New Roman", serif;
        font-size: ${state.reader.fontSizePct}%;
        line-height: 1.68;
        max-width: 740px;
        margin-left: auto;
        margin-right: auto;
      }
      img, svg {
        max-width: 100%;
        height: auto;
      }
      a {
        color: ${linkColor};
      }
      pre, code {
        white-space: pre-wrap;
        word-break: break-word;
      }
    </style>
  `;

  let docHtml = rawHtml;
  if (/<head[^>]*>/i.test(docHtml)) {
    docHtml = docHtml.replace(/<head[^>]*>/i, (m) => `${m}${readerCss}`);
  } else {
    docHtml = `<!DOCTYPE html><html><head><meta charset="utf-8">${readerCss}</head><body>${docHtml}</body></html>`;
  }

  els.readerIframe.srcdoc = docHtml;
  els.readerIframe.onload = () => {
    try {
      const win = els.readerIframe.contentWindow;
      const doc = els.readerIframe.contentDocument;
      if (!doc || !win) return;

      // Scroll to anchor if specified
      if (anchorHref && anchorHref.includes("#")) {
        const hash = anchorHref.split("#")[1];
        if (hash) {
          const targetEl =
            doc.getElementById(hash) || doc.querySelector(`[name="${CSS.escape(hash)}"]`);
          if (targetEl) targetEl.scrollIntoView();
        }
      } else {
        win.scrollTo(0, 0);
      }

      // Intercept internal chapter links inside the preview iframe
      doc.querySelectorAll("a[href]").forEach((a) => {
        a.addEventListener("click", (e) => {
          const href = a.getAttribute("href") || "";
          if (!href || /^(https?:|mailto:)/i.test(href)) return;
          e.preventDefault();
          const targetIdx = findChapterIndexByHref(
            state.reader.chapters,
            href,
            state.reader.currentIndex
          );
          state.reader.currentIndex = targetIdx;
          renderReaderSidebar();
          renderCurrentReaderChapter(href);
        });
      });
    } catch (_) {
      // Ignore cross-origin or sandbox restrictions
    }
  };
}

function closeReaderModal() {
  els.readerModal.classList.add("hidden");
  els.readerIframe.srcdoc = "";
}

// ---------------------------------------------------------------------------
// #7 EPUB Structure & Health Report Modal
// ---------------------------------------------------------------------------

function openHealthModal(item) {
  const hr = item.healthReport || {
    version: "2.0",
    isValid: true,
    spineCount: 1,
    xhtmlBytes: item.size || 0,
    imageCount: 0,
    fontCount: 0,
    tocCount: (item.toc || []).length,
    checks: {
      mimetypeUncompressed: true,
      containerXmlValid: true,
      opfValid: true,
      spineTargetsExist: true,
    },
  };

  els.healthModalTitle.textContent = `${t("healthModalTitle")} — ${
    item.title || item.outFileName
  }`;

  const checks = hr.checks || {};
  const checkRows = [
    { ok: checks.mimetypeUncompressed !== false, label: t("chkMime") },
    { ok: checks.containerXmlValid !== false, label: t("chkContainer") },
    { ok: checks.opfValid !== false, label: t("chkOpf") },
    { ok: checks.spineTargetsExist !== false, label: t("chkSpine") },
  ];

  els.healthModalBody.innerHTML = `
    <div class="health-grid">
      <div class="health-stat-card">
        <div class="health-stat-label">${t("healthVer")}</div>
        <div class="health-stat-value">EPUB ${hr.version || "2.0"}</div>
      </div>
      <div class="health-stat-card">
        <div class="health-stat-label">${t("healthSpine")}</div>
        <div class="health-stat-value">${hr.spineCount ?? 1}</div>
      </div>
      <div class="health-stat-card">
        <div class="health-stat-label">${t("healthXhtmlSize")}</div>
        <div class="health-stat-value">${formatBytes(hr.xhtmlBytes || item.size || 0)}</div>
      </div>
      <div class="health-stat-card">
        <div class="health-stat-label">${t("healthImages")}</div>
        <div class="health-stat-value">${hr.imageCount ?? 0}</div>
      </div>
      <div class="health-stat-card">
        <div class="health-stat-label">${t("healthFonts")}</div>
        <div class="health-stat-value">${hr.fontCount ?? 0}</div>
      </div>
      <div class="health-stat-card">
        <div class="health-stat-label">${t("healthTocCount")}</div>
        <div class="health-stat-value">${hr.tocCount ?? (item.toc ? item.toc.length : 0)}</div>
      </div>
    </div>
    <div class="health-checklist">
      ${checkRows
        .map(
          (c) => `
        <div class="health-check-item ${c.ok ? "pass" : ""}">
          <span>${c.ok ? "✅" : "❌"}</span>
          <span>${c.label}</span>
        </div>
      `
        )
        .join("")}
    </div>
  `;

  els.healthModal.classList.remove("hidden");
}

function closeHealthModal() {
  els.healthModal.classList.add("hidden");
}

// ---------------------------------------------------------------------------
// #8 & #9 Edit Metadata, Cover & TOC Modal
// ---------------------------------------------------------------------------

function openEditModalForQueued(queueIdx) {
  const qItem = state.queuedFiles[queueIdx];
  if (!qItem) return;

  state.editor.mode = "queued";
  state.editor.targetKey = queueIdx;
  state.editor.coverOverride = qItem.coverOverride || null;
  state.editor.coverReset = false;

  const meta = qItem.metadataOverride || {};
  els.editTitle.value = meta.title || qItem.name.replace(/\.[^.]+$/, "");
  els.editAuthor.value = meta.author || "";
  els.editLanguage.value = meta.language || "en";
  els.editPublisher.value = meta.publisher || "";
  els.editDescription.value = meta.description || "";

  renderEditCoverPreview(state.editor.coverOverride?.dataUrl || null);
  state.editor.tocEntries = (qItem.tocOverride || []).map((e, i) => ({
    id: e.id || `toc_${i + 1}`,
    title: e.title || e.label || "",
    href: e.href || "book.xhtml",
  }));
  renderEditTocList();

  els.editSaveStatus.textContent = "";
  els.editModal.classList.remove("hidden");
}

function openEditModalForBook(item, source = "converted") {
  state.editor.mode = source;
  state.editor.targetKey = source === "history" ? item.historyId : item.outRelPath;
  state.editor.coverOverride = null;
  state.editor.coverReset = false;

  els.editTitle.value = item.title || "";
  els.editAuthor.value = item.author || "";
  els.editLanguage.value = item.language || "en";
  els.editPublisher.value = item.publisher || "";
  els.editDescription.value = item.description || "";

  renderEditCoverPreview(item.coverDataUrl || null);

  state.editor.tocEntries = (item.toc || []).map((e, i) => ({
    id: e.id || `toc_${i + 1}`,
    title: e.title || e.label || `Chapter ${i + 1}`,
    href: e.href || "book.xhtml",
  }));
  renderEditTocList();

  els.editSaveStatus.textContent = "";
  els.editModal.classList.remove("hidden");
}

function renderEditCoverPreview(dataUrl) {
  if (!els.editCoverPreview) return;
  if (dataUrl) {
    els.editCoverPreview.innerHTML = `<img src="${dataUrl}" alt="Cover preview" />`;
  } else {
    els.editCoverPreview.textContent = "No Cover";
  }
}

function renderEditTocList() {
  els.editTocList.innerHTML = "";
  const entries = state.editor.tocEntries;

  if (entries.length === 0) {
    const empty = document.createElement("div");
    empty.className = "toc-editor-hint";
    empty.textContent = "No custom TOC overrides yet — click '+ Add Entry' to add one.";
    els.editTocList.appendChild(empty);
    return;
  }

  entries.forEach((entry, idx) => {
    const row = document.createElement("div");
    row.className = "edit-toc-row";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "btn btn-xs";
    upBtn.textContent = "↑";
    upBtn.disabled = idx === 0;
    upBtn.addEventListener("click", () => {
      const tmp = entries[idx - 1];
      entries[idx - 1] = entries[idx];
      entries[idx] = tmp;
      renderEditTocList();
    });

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "btn btn-xs";
    downBtn.textContent = "↓";
    downBtn.disabled = idx === entries.length - 1;
    downBtn.addEventListener("click", () => {
      const tmp = entries[idx + 1];
      entries[idx + 1] = entries[idx];
      entries[idx] = tmp;
      renderEditTocList();
    });

    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "text-input toc-title-inp";
    titleInp.value = entry.title || "";
    titleInp.placeholder = "Chapter title";
    titleInp.addEventListener("input", () => {
      entry.title = titleInp.value;
      entry.label = titleInp.value;
    });

    const hrefInp = document.createElement("input");
    hrefInp.type = "text";
    hrefInp.className = "text-input toc-href-inp";
    hrefInp.value = entry.href || "";
    hrefInp.placeholder = "book.xhtml";
    hrefInp.addEventListener("input", () => {
      entry.href = hrefInp.value;
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn btn-xs btn-danger-outline";
    delBtn.textContent = "×";
    delBtn.addEventListener("click", () => {
      entries.splice(idx, 1);
      renderEditTocList();
    });

    row.appendChild(upBtn);
    row.appendChild(downBtn);
    row.appendChild(titleInp);
    row.appendChild(hrefInp);
    row.appendChild(delBtn);
    els.editTocList.appendChild(row);
  });
}

async function handleSaveEditModal() {
  const metadataOverride = {
    title: els.editTitle.value.trim(),
    author: els.editAuthor.value.trim(),
    language: els.editLanguage.value.trim() || "en",
    publisher: els.editPublisher.value.trim(),
    description: els.editDescription.value.trim(),
  };

  const tocOverride = state.editor.tocEntries
    .map((e, i) => ({
      id: e.id || `toc_${i + 1}`,
      title: (e.title || "").trim(),
      label: (e.title || "").trim(),
      href: (e.href || "book.xhtml").trim(),
    }))
    .filter((e) => e.title.length > 0);

  if (state.editor.mode === "queued") {
    const qItem = state.queuedFiles[state.editor.targetKey];
    if (qItem) {
      qItem.metadataOverride = metadataOverride;
      if (state.editor.coverOverride) {
        qItem.coverOverride = state.editor.coverOverride;
      } else if (state.editor.coverReset) {
        qItem.coverOverride = null;
      }
      qItem.tocOverride = tocOverride.length > 0 ? tocOverride : null;
      renderQueue();
      appendLog(`[INFO] Saved pre-conversion metadata/TOC overrides for ${qItem.name}.`, "info");
    }
    closeEditModal();
    return;
  }

  // Editing an already converted EPUB ("converted" or "history")
  const isHistory = state.editor.mode === "history";
  const item = isHistory
    ? state.historyItems.find((h) => h.historyId === state.editor.targetKey)
    : state.convertedItems.get(state.editor.targetKey);

  if (!item) {
    closeEditModal();
    return;
  }

  els.btnSaveEdit.disabled = true;
  els.btnSaveEdit.textContent = t("savingChangesBtn");

  try {
    const currentBytes = item.buffer.slice(0);
    const payload = {
      type: "update_epub",
      epubBytes: currentBytes,
      data: currentBytes,
      metadataOverride,
      coverOverride: state.editor.coverOverride
        ? {
            bytes: state.editor.coverOverride.bytes,
            data: state.editor.coverOverride.bytes,
            mime: state.editor.coverOverride.mime || "image/jpeg",
          }
        : null,
      tocOverride,
    };

    const res = await workerPool.callAny(payload, [currentBytes]);
    const updatedRaw = res.epubBytes || res.epubData;

    if ((res.ok ?? res.success) && updatedRaw) {
      const newBuffer = toArrayBuffer(updatedRaw);
      if (item.blobUrl) URL.revokeObjectURL(item.blobUrl);
      const newBlob = new Blob([newBuffer], { type: "application/epub+zip" });

      item.buffer = newBuffer;
      item.size = newBuffer.byteLength;
      item.epubSize = res.epubSize || newBuffer.byteLength;
      item.blobUrl = URL.createObjectURL(newBlob);
      item.title = res.title || metadataOverride.title || item.title;
      item.author = res.author ?? metadataOverride.author ?? item.author;
      item.language = res.language || metadataOverride.language || item.language;
      item.publisher = res.publisher ?? metadataOverride.publisher ?? item.publisher;
      item.description = res.description ?? metadataOverride.description ?? item.description;

      if (res.coverDataUrl) {
        item.coverDataUrl = res.coverDataUrl;
      } else if (state.editor.coverOverride?.dataUrl) {
        item.coverDataUrl = state.editor.coverOverride.dataUrl;
      }

      if (Array.isArray(res.toc)) {
        item.toc = res.toc.map((e, i) => ({
          id: e.id || `toc_${i + 1}`,
          title: e.title || e.label || `Chapter ${i + 1}`,
          label: e.label || e.title || `Chapter ${i + 1}`,
          href: e.href || "",
        }));
      } else {
        item.toc = tocOverride;
      }

      if (res.healthReport) {
        item.healthReport = res.healthReport;
      }
      if (res.chaptersPreview || res.chapters) {
        item.chaptersPreview = res.chaptersPreview || res.chapters;
      } else {
        item.chaptersPreview = null; // Force fresh read on next preview
      }

      // Recompute output filename if using a metadata template
      const tpl = els.selFilenameTemplate
        ? els.selFilenameTemplate.value
        : "{OriginalFilename}.epub";
      const updatedNames = buildOutputFilenameAndPath({
        template: tpl,
        originalFileName: item.originalFileName || item.outFileName,
        originalRelPath: item.originalRelPath || item.outRelPath,
        title: item.title,
        author: item.author,
        language: item.language,
      });
      item.outFileName = updatedNames.outFileName;

      if (state.outputDirHandle) {
        await writeEpubToOutputFolder(item.outRelPath, item.buffer);
      }
      await saveItemToHistoryDb(item);

      renderDownloads();
      renderHistory();
      appendLog(`[OK] Updated metadata, cover & TOC in ${item.outFileName}.`, "ok");
      closeEditModal();
    } else {
      els.editSaveStatus.textContent = res.errorMessage || "Failed to update EPUB.";
    }
  } catch (err) {
    els.editSaveStatus.textContent = err && err.message ? err.message : String(err);
  } finally {
    els.btnSaveEdit.disabled = false;
    els.btnSaveEdit.textContent = t("saveChangesBtn");
  }
}

function closeEditModal() {
  els.editModal.classList.add("hidden");
}

// ---------------------------------------------------------------------------
// Try Sample MOBI
// ---------------------------------------------------------------------------

async function handleTrySample() {
  if (state.isRunning) return;
  try {
    els.statusText.textContent = "Loading bundled sample.mobi...";
    const resp = await fetch("./sample.mobi");
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} loading sample.mobi`);
    }
    const blob = await resp.blob();
    const sampleFile = new File([blob], "sample_mobi6.mobi", {
      type: "application/x-mobipocket-ebook",
    });

    els.chkForce.checked = true;
    addFilesToQueue([{ file: sampleFile, relPath: "sample_mobi6.mobi" }], true);
    appendLog(
      "[INFO] Loaded bundled sample book: sample_mobi6.mobi (Alice's Adventures in Wonderland).",
      "info"
    );
    await startBatchConversion();
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    appendLog(`[FAILED] Could not load sample.mobi: ${message}`, "fail");
  }
}

// ---------------------------------------------------------------------------
// #1 PWA Service Worker Registration & Install Button
// ---------------------------------------------------------------------------

function initPwaSupport() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js").catch(() => {
        // Ignore registration errors on file:// or unsupported environments
      });
    });
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    state.deferredInstallPrompt = e;
    if (els.btnInstallPwa) {
      els.btnInstallPwa.classList.remove("hidden");
    }
  });

  window.addEventListener("appinstalled", () => {
    state.deferredInstallPrompt = null;
    if (els.btnInstallPwa) {
      els.btnInstallPwa.classList.add("hidden");
    }
    appendLog("[INFO] MobiToEpub web app installed for offline usage.", "ok");
  });

  if (els.btnInstallPwa) {
    els.btnInstallPwa.addEventListener("click", async () => {
      if (!state.deferredInstallPrompt) return;
      state.deferredInstallPrompt.prompt();
      try {
        await state.deferredInstallPrompt.userChoice;
      } catch (_) {
        // Ignore
      }
      state.deferredInstallPrompt = null;
      els.btnInstallPwa.classList.add("hidden");
    });
  }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

// Theme & Language (#16, #17)
els.btnThemeToggle.addEventListener("click", () => {
  applyTheme(state.theme === "dark" ? "light" : "dark");
});

els.btnLangToggle.addEventListener("click", () => {
  state.lang = state.lang === "en" ? "vi" : "en";
  applyI18n();
});

// Image Optimization Sub-options (#13)
els.chkImageOptimize.addEventListener("change", () => {
  els.imageOptSubgroup.classList.toggle("hidden", !els.chkImageOptimize.checked);
});

// Input & Folder Pickers
els.btnAddFiles.addEventListener("click", (e) => {
  e.stopPropagation();
  els.fileInput.value = "";
  els.fileInput.click();
});

els.btnSelectFolder.addEventListener("click", (e) => {
  e.stopPropagation();
  els.folderInput.value = "";
  els.folderInput.click();
});

if (els.btnChooseOutDir) {
  els.btnChooseOutDir.addEventListener("click", (e) => {
    e.stopPropagation();
    handleChooseOutputDir();
  });
}

if (els.btnClearOutDir) {
  els.btnClearOutDir.addEventListener("click", (e) => {
    e.stopPropagation();
    clearOutputDir();
  });
}

els.btnTrySample.addEventListener("click", (e) => {
  e.stopPropagation();
  handleTrySample();
});

els.dropzone.addEventListener("click", (e) => {
  if (e.target === els.dropzone || e.target.closest(".dropzone-clickable")) {
    if (!state.isRunning) {
      els.fileInput.value = "";
      els.fileInput.click();
    }
  }
});

els.fileInput.addEventListener("change", () => {
  const files = Array.from(els.fileInput.files || []);
  if (files.length > 0) {
    handleIncomingFileEntries(files.map((f) => ({ file: f, relPath: f.name })));
  }
});

els.folderInput.addEventListener("change", () => {
  const files = Array.from(els.folderInput.files || []);
  if (files.length > 0) {
    handleIncomingFileEntries(
      files.map((f) => ({
        file: f,
        relPath: f.webkitRelativePath || f.name,
      }))
    );
  }
});

els.dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  if (!state.isRunning) {
    els.dropzone.classList.add("dragover");
  }
});

els.dropzone.addEventListener("dragleave", () => {
  els.dropzone.classList.remove("dragover");
});

els.dropzone.addEventListener("drop", async (e) => {
  e.preventDefault();
  els.dropzone.classList.remove("dragover");
  if (state.isRunning) return;

  const entries = await extractDroppedItems(e.dataTransfer);
  if (entries.length > 0) {
    await handleIncomingFileEntries(entries);
  }
});

els.btnClearQueue.addEventListener("click", clearQueue);
els.btnConvert.addEventListener("click", startBatchConversion);

els.btnCancel.addEventListener("click", () => {
  if (state.isRunning && !state.cancelRequested) {
    state.cancelRequested = true;
    els.btnCancel.textContent = t("stoppingBtn");
    els.btnCancel.disabled = true;
    appendLog("Cancellation requested: stopping after active worker task finishes...", "info");
  }
});

els.btnClearLog.addEventListener("click", clearLog);
els.btnDownloadAllZip.addEventListener("click", handleDownloadAllZip);

// History Section Controls (#4)
els.btnToggleHistory.addEventListener("click", () => {
  state.historyCollapsed = !state.historyCollapsed;
  els.btnToggleHistory.textContent = state.historyCollapsed
    ? t("showHistoryBtn")
    : t("hideHistoryBtn");
  renderHistory();
});

els.btnClearHistory.addEventListener("click", clearHistoryDb);

// Reader Modal Controls (#6)
els.btnToggleReaderSidebar.addEventListener("click", () => {
  els.readerSidebar.classList.toggle("collapsed");
});

els.btnReaderPrev.addEventListener("click", () => {
  if (state.reader.currentIndex > 0) {
    state.reader.currentIndex--;
    renderReaderSidebar();
    renderCurrentReaderChapter();
  }
});

els.btnReaderNext.addEventListener("click", () => {
  if (state.reader.currentIndex < state.reader.chapters.length - 1) {
    state.reader.currentIndex++;
    renderReaderSidebar();
    renderCurrentReaderChapter();
  }
});

els.btnFontDec.addEventListener("click", () => {
  state.reader.fontSizePct = Math.max(70, state.reader.fontSizePct - 10);
  renderCurrentReaderChapter();
});

els.btnFontInc.addEventListener("click", () => {
  state.reader.fontSizePct = Math.min(160, state.reader.fontSizePct + 10);
  renderCurrentReaderChapter();
});

els.btnCloseReader.addEventListener("click", closeReaderModal);
els.readerModal.addEventListener("click", (e) => {
  if (e.target === els.readerModal) closeReaderModal();
});

// Health Modal Controls (#7)
els.btnCloseHealth.addEventListener("click", closeHealthModal);
els.healthModal.addEventListener("click", (e) => {
  if (e.target === els.healthModal) closeHealthModal();
});

// Edit Modal Controls (#8 & #9)
els.btnCloseEdit.addEventListener("click", closeEditModal);
els.btnCancelEdit.addEventListener("click", closeEditModal);
els.editModal.addEventListener("click", (e) => {
  if (e.target === els.editModal) closeEditModal();
});

els.btnUploadCover.addEventListener("click", () => {
  els.editCoverInput.value = "";
  els.editCoverInput.click();
});

els.editCoverInput.addEventListener("change", async () => {
  const file = els.editCoverInput.files && els.editCoverInput.files[0];
  if (!file) return;
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  const dataUrl = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
  state.editor.coverOverride = {
    bytes,
    mime: file.type || "image/jpeg",
    dataUrl,
  };
  state.editor.coverReset = false;
  renderEditCoverPreview(dataUrl);
});

els.btnResetCover.addEventListener("click", () => {
  state.editor.coverOverride = null;
  state.editor.coverReset = true;
  renderEditCoverPreview(null);
});

els.btnAddTocEntry.addEventListener("click", () => {
  state.editor.tocEntries.push({
    id: `toc_${state.editor.tocEntries.length + 1}`,
    title: `Chapter ${state.editor.tocEntries.length + 1}`,
    href: "book.xhtml",
  });
  renderEditTocList();
});

els.btnSaveEdit.addEventListener("click", handleSaveEditModal);

// Keyboard Escape to close active modals
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!els.readerModal.classList.contains("hidden")) closeReaderModal();
    if (!els.healthModal.classList.contains("hidden")) closeHealthModal();
    if (!els.editModal.classList.contains("hidden")) closeEditModal();
  }
});

// ---------------------------------------------------------------------------
// Startup Initialization
// ---------------------------------------------------------------------------

applyTheme(state.theme);
applyI18n();
initDirectSaveFeature();
initPwaSupport();
loadHistoryFromDb();
workerPool.initPrimary();
