"""Tkinter GUI for mobi2epub converter."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mobi2epub.runner import (
    BatchSummary,
    Cancelled,
    FileDone,
    FileFailed,
    FileSkipped,
    FileStarted,
    Finished,
    RunnerEvent,
    RunnerOptions,
    Started,
    run_batch,
)


class WorkerError(RunnerEvent):
    def __init__(self, message: str):
        self.message = message


def open_folder_in_explorer(folder_path: Path | str) -> None:
    """Open the folder in OS file explorer."""
    p = Path(folder_path).resolve()
    if not p.exists():
        return
    if sys.platform == "win32":
        os.startfile(str(p))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def get_asset_path(filename: str) -> Optional[Path]:
    """Get absolute path to bundled asset, supporting PyInstaller _MEIPASS."""
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / filename
        if candidate.exists():
            return candidate

    # Development directory
    dev_path = Path(__file__).resolve().parent.parent / filename
    if dev_path.exists():
        return dev_path

    return None


class MobiToEpubApp:
    """Main application window for MOBI to EPUB conversion."""

    def __init__(self, root: Optional[tk.Tk] = None):
        self.root = root or tk.Tk()
        self.root.title("MOBI to EPUB Converter")
        self.root.geometry("680x600")
        self.root.minsize(580, 480)

        # Set window icon if available
        icon_path = get_asset_path("app_icon.ico")
        if icon_path and sys.platform == "win32":
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # State variables
        self.selected_inputs: list[Path] = []
        self.var_input_text = tk.StringVar(value="")
        self.var_output_text = tk.StringVar(value="")
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_force = tk.BooleanVar(value=False)

        self.var_status = tk.StringVar(value="Select input files/folder and an output folder.")
        self.var_summary = tk.StringVar(value="")
        self.var_elapsed = tk.StringVar(value="")

        self.event_queue: queue.Queue[RunnerEvent] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.start_time: float = 0.0
        self.is_running = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # 1. Input selection
        # -------------------------------------------------------------
        input_group = ttk.LabelFrame(main_frame, text="Input MOBI Files", padding="8")
        input_group.pack(fill=tk.X, pady=(0, 8))

        row1 = ttk.Frame(input_group)
        row1.pack(fill=tk.X, expand=True)

        self.entry_input = ttk.Entry(row1, textvariable=self.var_input_text)
        self.entry_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry_input.bind("<KeyRelease>", lambda e: self._on_input_changed())

        self.btn_add_files = ttk.Button(row1, text="Add files...", command=self._on_add_files)
        self.btn_add_files.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_select_folder = ttk.Button(row1, text="Select folder...", command=self._on_select_folder)
        self.btn_select_folder.pack(side=tk.LEFT)

        # -------------------------------------------------------------
        # 2. Output selection
        # -------------------------------------------------------------
        output_group = ttk.LabelFrame(main_frame, text="Output Folder (Required)", padding="8")
        output_group.pack(fill=tk.X, pady=(0, 8))

        row2 = ttk.Frame(output_group)
        row2.pack(fill=tk.X, expand=True)

        self.entry_output = ttk.Entry(row2, textvariable=self.var_output_text)
        self.entry_output.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry_output.bind("<KeyRelease>", lambda e: self._on_output_changed())

        self.btn_browse_output = ttk.Button(row2, text="Browse...", command=self._on_browse_output)
        self.btn_browse_output.pack(side=tk.LEFT)

        # -------------------------------------------------------------
        # 3. Options & Action Buttons
        # -------------------------------------------------------------
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=(0, 8))

        # Checkboxes on the left
        opts_frame = ttk.Frame(ctrl_frame)
        opts_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.chk_recursive = ttk.Checkbutton(
            opts_frame,
            text="Include subfolders",
            variable=self.var_recursive,
        )
        self.chk_recursive.pack(anchor=tk.W)

        self.chk_force = ttk.Checkbutton(
            opts_frame,
            text="Overwrite existing",
            variable=self.var_force,
        )
        self.chk_force.pack(anchor=tk.W)

        # Buttons on the right
        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_convert = ttk.Button(
            btn_frame,
            text="Convert",
            command=self._on_start_convert,
            width=12,
        )
        self.btn_convert.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_convert.state(["disabled"])  # Disabled initially until output is set

        self.btn_cancel = ttk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            width=10,
        )
        self.btn_cancel.pack(side=tk.LEFT)
        self.btn_cancel.state(["disabled"])

        # -------------------------------------------------------------
        # 4. Progress bar & Status
        # -------------------------------------------------------------
        prog_group = ttk.Frame(main_frame)
        prog_group.pack(fill=tk.X, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(prog_group, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        status_row = ttk.Frame(prog_group)
        status_row.pack(fill=tk.X)

        self.lbl_status = ttk.Label(status_row, textvariable=self.var_status, font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_elapsed = ttk.Label(status_row, textvariable=self.var_elapsed, font=("Segoe UI", 9))
        self.lbl_elapsed.pack(side=tk.RIGHT)

        # -------------------------------------------------------------
        # 5. Conversion Log
        # -------------------------------------------------------------
        log_group = ttk.LabelFrame(main_frame, text="Log", padding="6")
        log_group.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        log_frame = ttk.Frame(log_group)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_log = tk.Text(
            log_frame,
            wrap=tk.WORD,
            height=10,
            state="disabled",
            font=("Consolas", 9),
            bg="#ffffff",
            fg="#212121",
        )
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.txt_log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log["yscrollcommand"] = scrollbar.set

        # Configure log color tags
        self.txt_log.tag_config("ok", foreground="#2e7d32")
        self.txt_log.tag_config("skip", foreground="#ed6c02")
        self.txt_log.tag_config("fail", foreground="#d32f2f")
        self.txt_log.tag_config("info", foreground="#1565c0")
        self.txt_log.tag_config("bold", font=("Consolas", 9, "bold"))

        # -------------------------------------------------------------
        # 6. Bottom Summary & Open Output Folder
        # -------------------------------------------------------------
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)

        self.lbl_summary = ttk.Label(bottom_frame, textvariable=self.var_summary, font=("Segoe UI", 9, "bold"))
        self.lbl_summary.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_open_folder = ttk.Button(
            bottom_frame,
            text="Open output folder",
            command=self._on_open_output_folder,
        )
        self.btn_open_folder.pack(side=tk.RIGHT)
        self.btn_open_folder.state(["disabled"])

    # -----------------------------------------------------------------
    # Event Handlers & Validation
    # -----------------------------------------------------------------

    def _append_log(self, text: str, tag: Optional[str] = None) -> None:
        self.txt_log.config(state="normal")
        if tag:
            self.txt_log.insert(tk.END, text + "\n", tag)
        else:
            self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def _clear_log(self) -> None:
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state="disabled")

    def _on_add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select MOBI Book(s)",
            filetypes=[
                ("MOBI books", "*.mobi;*.prc;*.azw3;*.azw"),
                ("All files", "*.*"),
            ],
        )
        if files:
            paths = [Path(f) for f in files]
            self.selected_inputs = paths
            if len(paths) == 1:
                self.var_input_text.set(str(paths[0]))
            else:
                self.var_input_text.set(f"{len(paths)} files selected: {paths[0].name}, ...")
            # Auto-suggest output folder if empty
            if not self.var_output_text.get().strip():
                self.var_output_text.set(str(paths[0].parent))
            self._update_convert_button_state()

    def _on_select_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Folder Containing MOBI Files")
        if folder:
            p = Path(folder)
            self.selected_inputs = [p]
            self.var_input_text.set(str(p))
            if not self.var_output_text.get().strip():
                self.var_output_text.set(str(p))
            self._update_convert_button_state()

    def _on_browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder for EPUBs")
        if folder:
            self.var_output_text.set(str(Path(folder)))
            self._update_convert_button_state()

    def _on_input_changed(self) -> None:
        val = self.var_input_text.get().strip()
        if val:
            p = Path(val)
            self.selected_inputs = [p]
        else:
            self.selected_inputs = []
        self._update_convert_button_state()

    def _on_output_changed(self) -> None:
        self._update_convert_button_state()

    def _is_output_writable(self, path: Path) -> bool:
        """Check if output directory is writable or can be created."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / f".write_test_{os.getpid()}_{time.time_ns()}.tmp"
            test_file.write_bytes(b"test")
            test_file.unlink()
            return True
        except Exception:
            return False

    def _update_convert_button_state(self) -> None:
        if self.is_running:
            return

        out_str = self.var_output_text.get().strip()
        has_input = bool(self.selected_inputs or self.var_input_text.get().strip())

        if has_input and out_str:
            out_path = Path(out_str)
            if self._is_output_writable(out_path):
                self.btn_convert.state(["!disabled"])
                return

        self.btn_convert.state(["disabled"])

    # -----------------------------------------------------------------
    # Conversion Execution
    # -----------------------------------------------------------------

    def _on_start_convert(self) -> None:
        out_str = self.var_output_text.get().strip()
        if not out_str:
            messagebox.showerror("Error", "Output folder is required.")
            return

        out_path = Path(out_str)
        if not self._is_output_writable(out_path):
            messagebox.showerror("Error", f"Output folder is not writable:\n{out_path}")
            return

        input_val = self.var_input_text.get().strip()
        if not self.selected_inputs and input_val:
            self.selected_inputs = [Path(input_val)]

        if not self.selected_inputs:
            messagebox.showerror("Error", "Please select input MOBI files or a folder.")
            return

        # Prepare UI for running
        self.is_running = True
        self.cancel_event.clear()
        self.start_time = time.time()
        self._clear_log()

        self.btn_convert.state(["disabled"])
        self.btn_add_files.state(["disabled"])
        self.btn_select_folder.state(["disabled"])
        self.btn_browse_output.state(["disabled"])
        self.entry_input.state(["disabled"])
        self.entry_output.state(["disabled"])
        self.chk_recursive.state(["disabled"])
        self.chk_force.state(["disabled"])
        self.btn_open_folder.state(["disabled"])

        self.btn_cancel.state(["!disabled"])
        self.btn_cancel.config(text="Cancel")

        self.progress_bar.config(mode="determinate", value=0, maximum=100)
        self.var_status.set("Scanning input files...")
        self.var_summary.set("")
        self.var_elapsed.set("Elapsed: 00:00")

        # Start worker thread
        options = RunnerOptions(
            recursive=self.var_recursive.get(),
            force=self.var_force.get(),
            engine="kindleunpack",
            jobs=1,  # Window always runs one file at a time, no process pool!
        )

        inputs_to_run = list(self.selected_inputs)
        self.worker_thread = threading.Thread(
            target=self._worker_thread_func,
            args=(inputs_to_run, out_path, options),
            daemon=True,
        )
        self.worker_thread.start()

        # Start polling queue
        self.root.after(100, self._poll_queue)

    def _worker_thread_func(self, inputs: list[Path], out_dir: Path, options: RunnerOptions) -> None:
        try:
            run_batch(
                inputs=inputs,
                out_dir=out_dir,
                options=options,
                on_event=self.event_queue.put,
                cancel_event=self.cancel_event,
            )
        except Exception as e:
            self.event_queue.put(WorkerError(f"Unexpected error: {e}"))

    def _poll_queue(self) -> None:
        # Update elapsed time
        if self.is_running:
            elapsed_sec = int(time.time() - self.start_time)
            mins = elapsed_sec // 60
            secs = elapsed_sec % 60
            self.var_elapsed.set(f"Elapsed: {mins:02d}:{secs:02d}")

        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            self._handle_event(event)

        if self.is_running:
            self.root.after(100, self._poll_queue)

    def _handle_event(self, event: RunnerEvent) -> None:
        if isinstance(event, Started):
            if event.total == 0:
                self.var_status.set("No .mobi files found.")
                self._append_log("No .mobi files found in selected input.", "fail")
                return

            if event.total == 1:
                # Indeterminate for single file
                self.progress_bar.config(mode="indeterminate")
                self.progress_bar.start(15)
            else:
                self.progress_bar.config(mode="determinate", maximum=event.total, value=0)

            self.var_status.set(f"Found {event.total} file(s). Starting conversion...")
            self._append_log(f"Starting conversion of {event.total} file(s)...", "info")

        elif isinstance(event, FileStarted):
            display_name = event.name
            self.var_status.set(f"{event.index} / {event.total} · {display_name}")

        elif isinstance(event, FileDone):
            if self.progress_bar["mode"] == "determinate":
                self.progress_bar["value"] = event.index
            title_str = f" ('{event.title}')" if event.title else ""
            self._append_log(f"[OK] {event.rel_path} -> {event.dst_path.name}{title_str}", "ok")

        elif isinstance(event, FileSkipped):
            if self.progress_bar["mode"] == "determinate":
                self.progress_bar["value"] = event.index
            self._append_log(f"[SKIPPED] {event.rel_path} ({event.reason})", "skip")

        elif isinstance(event, FileFailed):
            if self.progress_bar["mode"] == "determinate":
                self.progress_bar["value"] = event.index
            badge = f"[{event.error_type.upper()}]" if event.error_type else "[FAILED]"
            self._append_log(f"[FAILED] {event.rel_path} {badge}: {event.reason}", "fail")

        elif isinstance(event, Cancelled):
            self._on_run_finished(event.summary, cancelled=True)

        elif isinstance(event, Finished):
            self._on_run_finished(event.summary, cancelled=False)

        elif isinstance(event, WorkerError):
            self._append_log(f"[ERROR] {event.message}", "fail")
            self._on_run_finished(None, cancelled=False, error_msg=event.message)

    def _on_run_finished(self, summary: Optional[BatchSummary], cancelled: bool, error_msg: Optional[str] = None) -> None:
        self.is_running = False
        if self.progress_bar["mode"] == "indeterminate":
            self.progress_bar.stop()

        if summary:
            if not cancelled:
                self.progress_bar.config(mode="determinate", value=summary.total, maximum=max(1, summary.total))
                status_txt = f"Finished in {summary.elapsed_seconds:.1f}s"
            else:
                status_txt = f"Stopped by user ({len(summary.converted)} converted, {len(summary.skipped)} skipped, {len(summary.failed)} failed)"

            self.var_status.set(status_txt)
            sum_text = f"Summary: Converted: {len(summary.converted)}  |  Skipped: {len(summary.skipped)}  |  Failed: {len(summary.failed)}"
            self.var_summary.set(sum_text)
            self._append_log(f"\n=== {sum_text} (Time: {summary.elapsed_seconds:.2f}s) ===", "bold")
        elif error_msg:
            self.var_status.set(f"Error: {error_msg}")
        else:
            self.var_status.set("Completed.")

        # Re-enable inputs and controls
        self.btn_add_files.state(["!disabled"])
        self.btn_select_folder.state(["!disabled"])
        self.btn_browse_output.state(["!disabled"])
        self.entry_input.state(["!disabled"])
        self.entry_output.state(["!disabled"])
        self.chk_recursive.state(["!disabled"])
        self.chk_force.state(["!disabled"])

        self.btn_cancel.state(["disabled"])
        self.btn_cancel.config(text="Cancel")
        self._update_convert_button_state()

        out_str = self.var_output_text.get().strip()
        if out_str and Path(out_str).exists():
            self.btn_open_folder.state(["!disabled"])

    def _on_cancel(self) -> None:
        if self.is_running and not self.cancel_event.is_set():
            self.cancel_event.set()
            self.btn_cancel.config(text="Stopping...")
            self.btn_cancel.state(["disabled"])
            self.var_status.set("Stopping after current file finishes...")
            self._append_log("Cancellation requested: stopping after current file...", "info")

    def _on_open_output_folder(self) -> None:
        out_str = self.var_output_text.get().strip()
        if out_str:
            open_folder_in_explorer(out_str)

    def _on_close(self) -> None:
        if self.is_running:
            if messagebox.askyesno("Exit", "Conversion is in progress. Stop and exit?"):
                self.cancel_event.set()
                self.root.destroy()
        else:
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = MobiToEpubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
