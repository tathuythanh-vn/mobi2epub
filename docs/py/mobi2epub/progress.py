"""Progress tracking with tqdm and final summary reporting."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from tqdm import tqdm


@dataclass
class FailureItem:
    path: Path
    error_type: str
    reason: str


@dataclass
class SkippedItem:
    path: Path
    reason: str


@dataclass
class ConvertedItem:
    src: Path
    dst: Path
    title: Optional[str] = None


class ProgressManager:
    """Manages tqdm progress bar display on stderr."""

    def __init__(self, total: int, quiet: bool = False):
        self.total = total
        self.quiet = quiet
        # Progress bar is shown only for multiple files and when not quiet
        self.show_bar = (total > 1) and (not quiet)
        self.bar: Optional[tqdm] = None

        if self.show_bar:
            self.bar = tqdm(
                total=total,
                desc="Converting",
                unit="file",
                file=sys.stderr,
                dynamic_ncols=True,
                bar_format="{desc}: {n_fmt}/{total_fmt} [{bar}] {postfix}",
            )

    def update_file(self, filename: str) -> None:
        """Update description/postfix with current filename."""
        if self.bar is not None:
            # Truncate if filename is very long
            display_name = filename if len(filename) <= 30 else filename[:27] + "..."
            self.bar.set_postfix_str(display_name)

    def advance(self, n: int = 1) -> None:
        if self.bar is not None:
            self.bar.update(n)

    def close(self) -> None:
        if self.bar is not None:
            self.bar.close()


class SummaryTracker:
    """Collects results and prints a structured summary report."""

    def __init__(self):
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.converted: list[ConvertedItem] = []
        self.skipped: list[SkippedItem] = []
        self.failed: list[FailureItem] = []

    def record_converted(self, src: Path, dst: Path, title: Optional[str] = None) -> None:
        self.converted.append(ConvertedItem(src=src, dst=dst, title=title))

    def record_skipped(self, path: Path, reason: str = "Destination already exists") -> None:
        self.skipped.append(SkippedItem(path=path, reason=reason))

    def record_failed(self, path: Path, error_type: str, reason: str) -> None:
        self.failed.append(FailureItem(path=path, error_type=error_type, reason=reason))

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or time.time()
        return max(0.0, end - self.start_time)

    def print_summary(self, quiet: bool = False, file=None) -> None:
        """Print the conversion summary."""
        out_file = sys.stdout if file is None else file
        if quiet and not self.failed:
            return

        elapsed = self.elapsed_seconds
        total_items = len(self.converted) + len(self.skipped) + len(self.failed)

        lines = [
            "",
            "=== Conversion Summary ===",
            f"Total files: {total_items} | Converted: {len(self.converted)} | Skipped: {len(self.skipped)} | Failed: {len(self.failed)}",
            f"Total time:  {elapsed:.2f}s",
        ]

        if self.failed:
            lines.append("\nFailures:")
            for item in self.failed:
                badge = f"[{item.error_type.upper()}]" if item.error_type else "[ERROR]"
                lines.append(f"  * {badge} {item.path.name}: {item.reason}")

        if not quiet and self.skipped:
            lines.append("\nSkipped (use --force to overwrite):")
            for item in self.skipped:
                lines.append(f"  * {item.path.name}: {item.reason}")

        output_str = "\n".join(lines) + "\n"
        out_file.write(output_str)
        out_file.flush()
