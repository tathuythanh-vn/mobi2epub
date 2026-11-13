"""Command-line interface for mobi2epub converter."""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from mobi2epub.collector import ConversionTask, collect_tasks
from mobi2epub.engines import ENGINES, get_engine
from mobi2epub.precheck import check_mobi_file
from mobi2epub.progress import ProgressManager, SummaryTracker


@dataclass
class TaskResult:
    src: Path
    dst: Path
    converted: bool
    skipped: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    title: Optional[str] = None


def convert_worker(
    src_str: str,
    dst_str: str,
    engine_name: str,
    force: bool,
) -> TaskResult:
    """Worker function for single-file conversion (compatible with ProcessPoolExecutor)."""
    src = Path(src_str)
    dst = Path(dst_str)

    # Overwrite check
    if not force and dst.exists():
        return TaskResult(
            src=src,
            dst=dst,
            converted=False,
            skipped=True,
            error_message="Destination already exists",
        )

    # Pre-check header and DRM
    precheck = check_mobi_file(src)
    if not precheck.is_valid:
        return TaskResult(
            src=src,
            dst=dst,
            converted=False,
            skipped=False,
            error_type="corrupt",
            error_message=precheck.error_reason or "Corrupt MOBI file",
            title=precheck.title,
        )

    if precheck.is_drm:
        return TaskResult(
            src=src,
            dst=dst,
            converted=False,
            skipped=False,
            error_type="drm",
            error_message="DRM protected: book is encrypted and cannot be converted",
            title=precheck.title,
        )

    try:
        engine = get_engine(engine_name)
        res = engine.convert(src, dst)
        if res.success:
            return TaskResult(
                src=src,
                dst=dst,
                converted=True,
                skipped=False,
                title=res.title or precheck.title,
            )
        else:
            return TaskResult(
                src=src,
                dst=dst,
                converted=False,
                skipped=False,
                error_type=res.error_type or "conversion_failed",
                error_message=res.error_message or "Conversion failed",
                title=res.title or precheck.title,
            )
    except Exception as e:
        return TaskResult(
            src=src,
            dst=dst,
            converted=False,
            skipped=False,
            error_type="exception",
            error_message=str(e),
            title=precheck.title,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mobi2epub",
        description="Convert MOBI books to standard EPUB files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "input",
        help="Input .mobi file or directory containing .mobi files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output destination directory (defaults to input file directory, or current folder for directory input).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan subdirectories for MOBI files (mirrors directory structure in output).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing EPUB files. Default behavior is to skip them.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress bar and non-essential messages.",
    )
    parser.add_argument(
        "--engine",
        choices=list(ENGINES.keys()),
        default="kindleunpack",
        help="Conversion engine backend to use.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        help="Number of concurrent workers for parallel conversion.",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        sys.stderr.write(f"Error: Input path '{args.input}' does not exist.\n")
        return 2

    # Check engine availability
    try:
        engine = get_engine(args.engine)
        if not engine.is_available():
            sys.stderr.write(
                f"Error: Selected engine '{args.engine}' is not available on this system.\n"
            )
            return 2
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 2

    # Collect files
    try:
        tasks = collect_tasks(
            input_path=input_path,
            output_dir=args.output,
            recursive=args.recursive,
        )
    except Exception as e:
        sys.stderr.write(f"Error collecting input files: {e}\n")
        return 2

    if not tasks:
        sys.stderr.write(f"Error: No .mobi files found in '{args.input}'.\n")
        return 2

    tracker = SummaryTracker()
    progress = ProgressManager(total=len(tasks), quiet=args.quiet)

    # Conversion execution (serial or parallel)
    jobs = max(1, args.jobs)
    if jobs > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            future_to_task = {
                executor.submit(
                    convert_worker,
                    str(t.src_path),
                    str(t.dst_path),
                    args.engine,
                    args.force,
                ): t
                for t in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    res: TaskResult = future.result()
                    if res.converted:
                        tracker.record_converted(res.src, res.dst, res.title)
                    elif res.skipped:
                        tracker.record_skipped(res.src, res.error_message or "Already exists")
                    else:
                        tracker.record_failed(res.src, res.error_type or "error", res.error_message or "Failed")
                except Exception as e:
                    tracker.record_failed(task.src_path, "process_error", str(e))

                progress.update_file(task.src_path.name)
                progress.advance(1)
    else:
        for t in tasks:
            progress.update_file(t.src_path.name)
            res = convert_worker(
                str(t.src_path),
                str(t.dst_path),
                args.engine,
                args.force,
            )
            if res.converted:
                tracker.record_converted(res.src, res.dst, res.title)
            elif res.skipped:
                tracker.record_skipped(res.src, res.error_message or "Already exists")
            else:
                tracker.record_failed(res.src, res.error_type or "error", res.error_message or "Failed")

            progress.advance(1)

    progress.close()
    tracker.finish()
    tracker.print_summary(quiet=args.quiet)

    # Exit code:
    # 0 if all succeeded (or skipped)
    # 1 if any failed
    if tracker.failed:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
