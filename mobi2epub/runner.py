"""Batch runner: orchestrates conversion tasks, manages execution modes, and emits events."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Union

from mobi2epub.collector import ConversionTask, collect_tasks
from mobi2epub.engines import get_engine
from mobi2epub.precheck import check_mobi_file


# ---------------------------------------------------------------------------
# Runner Options & Summary Data Structures
# ---------------------------------------------------------------------------

@dataclass
class RunnerOptions:
    recursive: bool = False
    force: bool = False
    engine: str = "kindleunpack"
    jobs: int = 1


@dataclass
class ConvertedItem:
    src: Path
    dst: Path
    title: Optional[str] = None


@dataclass
class SkippedItem:
    src: Path
    reason: str


@dataclass
class FailedItem:
    src: Path
    error_type: str
    reason: str


@dataclass
class BatchSummary:
    total: int
    converted: list[ConvertedItem] = field(default_factory=list)
    skipped: list[SkippedItem] = field(default_factory=list)
    failed: list[FailedItem] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    cancelled: bool = False

    @property
    def exit_code(self) -> int:
        if self.cancelled or self.failed:
            return 1
        return 0


# ---------------------------------------------------------------------------
# Events emitted by runner
# ---------------------------------------------------------------------------

class RunnerEvent:
    """Base event class."""
    pass


@dataclass
class Started(RunnerEvent):
    total: int


@dataclass
class FileStarted(RunnerEvent):
    index: int
    total: int
    name: str
    rel_path: Path
    src_path: Path


@dataclass
class FileDone(RunnerEvent):
    index: int
    total: int
    name: str
    rel_path: Path
    src_path: Path
    dst_path: Path
    title: Optional[str] = None


@dataclass
class FileSkipped(RunnerEvent):
    index: int
    total: int
    name: str
    rel_path: Path
    src_path: Path
    reason: str


@dataclass
class FileFailed(RunnerEvent):
    index: int
    total: int
    name: str
    rel_path: Path
    src_path: Path
    error_type: str
    reason: str


@dataclass
class Cancelled(RunnerEvent):
    summary: BatchSummary


@dataclass
class Finished(RunnerEvent):
    summary: BatchSummary


# ---------------------------------------------------------------------------
# Worker for parallel jobs
# ---------------------------------------------------------------------------

def _parallel_worker(
    src_str: str,
    dst_str: str,
    engine_name: str,
    force: bool,
) -> tuple[str, str, bool, bool, Optional[str], Optional[str], Optional[str]]:
    """Worker function for ProcessPoolExecutor (jobs > 1 only)."""
    src = Path(src_str)
    dst = Path(dst_str)

    if not force and dst.exists():
        return (src_str, dst_str, False, True, None, "Destination already exists", None)

    precheck = check_mobi_file(src)
    if not precheck.is_valid:
        return (src_str, dst_str, False, False, "corrupt", precheck.error_reason or "Corrupt file", precheck.title)

    if precheck.is_drm:
        return (
            src_str,
            dst_str,
            False,
            False,
            "drm",
            "DRM protected: book is encrypted and cannot be converted",
            precheck.title,
        )

    try:
        engine = get_engine(engine_name)
        res = engine.convert(src, dst)
        if res.success:
            return (src_str, dst_str, True, False, None, None, res.title or precheck.title)
        return (src_str, dst_str, False, False, res.error_type or "error", res.error_message or "Failed", res.title or precheck.title)
    except Exception as e:
        return (src_str, dst_str, False, False, "exception", str(e), precheck.title)


# ---------------------------------------------------------------------------
# Main run_batch Entry Point
# ---------------------------------------------------------------------------

def run_batch(
    inputs: Union[str, Path, Sequence[Union[str, Path]]],
    out_dir: str | Path | None = None,
    options: Optional[RunnerOptions] = None,
    on_event: Optional[Callable[[RunnerEvent], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> BatchSummary:
    """Run batch conversion across collected MOBI files.

    - When options.jobs == 1: Runs synchronously in current process without spawning processes.
    - When options.jobs > 1: Uses ProcessPoolExecutor (CLI parallel mode).
    """
    if options is None:
        options = RunnerOptions()

    def emit(evt: RunnerEvent) -> None:
        if on_event is not None:
            on_event(evt)

    start_time = time.time()
    summary = BatchSummary(total=0)

    # 1. Collect files
    try:
        tasks = collect_tasks(
            input_path=inputs,
            output_dir=out_dir,
            recursive=options.recursive,
        )
    except Exception as e:
        summary.failed.append(FailedItem(src=Path(str(inputs)), error_type="collector", reason=str(e)))
        summary.elapsed_seconds = max(0.0, time.time() - start_time)
        emit(Finished(summary))
        return summary

    total = len(tasks)
    summary.total = total
    emit(Started(total=total))

    if total == 0:
        summary.elapsed_seconds = max(0.0, time.time() - start_time)
        emit(Finished(summary))
        return summary

    # Verify engine availability before starting
    try:
        engine = get_engine(options.engine)
        if not engine.is_available():
            for task in tasks:
                summary.failed.append(
                    FailedItem(
                        src=task.src_path,
                        error_type="engine_unavailable",
                        reason=f"Engine '{options.engine}' is not available on this system",
                    )
                )
            summary.elapsed_seconds = max(0.0, time.time() - start_time)
            emit(Finished(summary))
            return summary
    except Exception as e:
        for task in tasks:
            summary.failed.append(FailedItem(src=task.src_path, error_type="engine_error", reason=str(e)))
        summary.elapsed_seconds = max(0.0, time.time() - start_time)
        emit(Finished(summary))
        return summary

    # 2. Execution mode: In-process (jobs == 1) vs ProcessPool (jobs > 1)
    if options.jobs <= 1 or total == 1:
        # In-process single-threaded execution (window & default CLI)
        for idx, task in enumerate(tasks, start=1):
            if cancel_event is not None and cancel_event.is_set():
                summary.cancelled = True
                break

            emit(FileStarted(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path))

            # Overwrite check
            if not options.force and task.dst_path.exists():
                summary.skipped.append(SkippedItem(src=task.src_path, reason="Destination already exists"))
                emit(FileSkipped(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path, reason="Destination already exists"))
                continue

            # Header pre-check
            precheck = check_mobi_file(task.src_path)
            if not precheck.is_valid:
                reason = precheck.error_reason or "Corrupt MOBI file"
                summary.failed.append(FailedItem(src=task.src_path, error_type="corrupt", reason=reason))
                emit(FileFailed(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path, error_type="corrupt", reason=reason))
                continue

            if precheck.is_drm:
                reason = "DRM protected: book is encrypted and cannot be converted"
                summary.failed.append(FailedItem(src=task.src_path, error_type="drm", reason=reason))
                emit(FileFailed(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path, error_type="drm", reason=reason))
                continue

            # Convert using engine
            try:
                res = engine.convert(task.src_path, task.dst_path)
                if res.success:
                    summary.converted.append(ConvertedItem(src=task.src_path, dst=task.dst_path, title=res.title or precheck.title))
                    emit(FileDone(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path, dst_path=task.dst_path, title=res.title or precheck.title))
                else:
                    err_type = res.error_type or "conversion_failed"
                    reason = res.error_message or "Conversion failed"
                    summary.failed.append(FailedItem(src=task.src_path, error_type=err_type, reason=reason))
                    emit(FileFailed(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path, error_type=err_type, reason=reason))
            except Exception as e:
                summary.failed.append(FailedItem(src=task.src_path, error_type="exception", reason=str(e)))
                emit(FileFailed(index=idx, total=total, name=task.src_path.name, rel_path=task.rel_path, src_path=task.src_path, error_type="exception", reason=str(e)))

    else:
        # Multi-process execution for CLI --jobs > 1
        with ProcessPoolExecutor(max_workers=options.jobs) as executor:
            future_to_task = {
                executor.submit(
                    _parallel_worker,
                    str(t.src_path),
                    str(t.dst_path),
                    options.engine,
                    options.force,
                ): (idx, t)
                for idx, t in enumerate(tasks, start=1)
            }

            for future in as_completed(future_to_task):
                idx, t = future_to_task[future]
                if cancel_event is not None and cancel_event.is_set():
                    summary.cancelled = True
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    break

                try:
                    src_s, dst_s, converted, skipped, err_type, err_msg, title = future.result()
                    if converted:
                        summary.converted.append(ConvertedItem(src=t.src_path, dst=t.dst_path, title=title))
                        emit(FileDone(index=idx, total=total, name=t.src_path.name, rel_path=t.rel_path, src_path=t.src_path, dst_path=t.dst_path, title=title))
                    elif skipped:
                        summary.skipped.append(SkippedItem(src=t.src_path, reason=err_msg or "Destination already exists"))
                        emit(FileSkipped(index=idx, total=total, name=t.src_path.name, rel_path=t.rel_path, src_path=t.src_path, reason=err_msg or "Destination already exists"))
                    else:
                        summary.failed.append(FailedItem(src=t.src_path, error_type=err_type or "error", reason=err_msg or "Failed"))
                        emit(FileFailed(index=idx, total=total, name=t.src_path.name, rel_path=t.rel_path, src_path=t.src_path, error_type=err_type or "error", reason=err_msg or "Failed"))
                except Exception as e:
                    summary.failed.append(FailedItem(src=t.src_path, error_type="process_error", reason=str(e)))
                    emit(FileFailed(index=idx, total=total, name=t.src_path.name, rel_path=t.rel_path, src_path=t.src_path, error_type="process_error", reason=str(e)))

    summary.elapsed_seconds = max(0.0, time.time() - start_time)

    if summary.cancelled:
        emit(Cancelled(summary=summary))
    else:
        emit(Finished(summary=summary))

    return summary
