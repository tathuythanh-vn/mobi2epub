"""Thin command-line interface for mobi2epub converter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from mobi2epub.engines import AVAILABLE_ENGINES, get_engine
from mobi2epub.progress import ProgressManager, SummaryTracker
from mobi2epub.runner import (
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
        choices=AVAILABLE_ENGINES,
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

    tracker = SummaryTracker()
    progress: Optional[ProgressManager] = None

    def on_event(event: RunnerEvent) -> None:
        nonlocal progress
        if isinstance(event, Started):
            progress = ProgressManager(total=event.total, quiet=args.quiet)
        elif isinstance(event, FileStarted):
            if progress is not None:
                progress.update_file(event.name)
        elif isinstance(event, FileDone):
            if progress is not None:
                progress.advance(1)
            tracker.record_converted(event.src_path, event.dst_path, event.title)
        elif isinstance(event, FileSkipped):
            if progress is not None:
                progress.advance(1)
            tracker.record_skipped(event.src_path, event.reason)
        elif isinstance(event, FileFailed):
            if progress is not None:
                progress.advance(1)
            tracker.record_failed(event.src_path, event.error_type, event.reason)

    options = RunnerOptions(
        recursive=args.recursive,
        force=args.force,
        engine=args.engine,
        jobs=max(1, args.jobs),
    )

    summary = run_batch(
        inputs=input_path,
        out_dir=args.output,
        options=options,
        on_event=on_event,
    )

    if progress is not None:
        progress.close()

    if summary.total == 0:
        sys.stderr.write(f"Error: No .mobi files found in '{args.input}'.\n")
        return 2

    tracker.finish()
    tracker.print_summary(quiet=args.quiet)

    if summary.failed or summary.cancelled:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
