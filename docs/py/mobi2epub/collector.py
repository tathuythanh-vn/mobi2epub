"""File collector: find and naturally sort MOBI files, computing output paths with mirroring."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Union

# Supported input extensions
SUPPORTED_EXTENSIONS = {".mobi", ".prc", ".azw3", ".azw"}


@dataclass
class ConversionTask:
    src_path: Path
    dst_path: Path
    rel_path: Path

    @property
    def output_exists(self) -> bool:
        return self.dst_path.exists()


def natural_sort_key(path: Path | str) -> list[int | str]:
    """Key for natural sorting (e.g. book1.mobi, book2.mobi, book10.mobi)."""
    s = str(path)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", s)]


def collect_tasks(
    input_path: Union[str, Path, Sequence[Union[str, Path]]],
    output_dir: str | Path | None = None,
    recursive: bool = False,
    allowed_extensions: Sequence[str] = (".mobi",),
) -> list[ConversionTask]:
    """Collect MOBI files to convert and compute their destination EPUB paths.

    Rules:
      - If input_path is a list of paths:
          - Multiple files/folders are collected and aggregated.
      - If input_path is a single file:
          - Default output destination is the file's parent directory.
          - If output_dir is specified, destination is output_dir / <filename>.epub.
      - If input_path is a directory:
          - Searches input_path for files matching allowed_extensions (case-insensitive).
          - If recursive=True, searches subdirectories.
          - Output structure mirrors input relative directory structure when output_dir is given.
          - If output_dir is None, defaults to current working directory (maintaining subfolder structure).
    """
    valid_exts = {ext.lower() for ext in allowed_extensions}
    out_root = Path(output_dir).resolve() if output_dir is not None else None

    # Handle sequence of inputs (e.g. from GUI file picker)
    if isinstance(input_path, (list, tuple)):
        if not input_path:
            return []
        all_tasks: list[ConversionTask] = []
        for item in input_path:
            item_path = Path(item).resolve()
            if not item_path.exists():
                raise FileNotFoundError(f"Input path does not exist: {item_path}")
            if item_path.is_file():
                if item_path.suffix.lower() in valid_exts:
                    dst_dir = out_root if out_root is not None else item_path.parent
                    dst_path = dst_dir / f"{item_path.stem}.epub"
                    all_tasks.append(
                        ConversionTask(
                            src_path=item_path,
                            dst_path=dst_path,
                            rel_path=Path(item_path.name),
                        )
                    )
            elif item_path.is_dir():
                sub_tasks = collect_tasks(
                    item_path,
                    output_dir=out_root,
                    recursive=recursive,
                    allowed_extensions=allowed_extensions,
                )
                all_tasks.extend(sub_tasks)
        all_tasks.sort(key=lambda t: natural_sort_key(t.src_path))
        return all_tasks

    root = Path(input_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input path does not exist: {root}")

    tasks: list[ConversionTask] = []

    if root.is_file():
        if root.suffix.lower() not in valid_exts:
            raise ValueError(f"File '{root.name}' does not have a supported extension ({', '.join(sorted(valid_exts))})")

        dst_dir = out_root if out_root is not None else root.parent
        dst_path = dst_dir / f"{root.stem}.epub"
        tasks.append(
            ConversionTask(
                src_path=root,
                dst_path=dst_path,
                rel_path=Path(root.name),
            )
        )
        return tasks

    if not root.is_dir():
        raise ValueError(f"Input path is neither a regular file nor a directory: {root}")

    # Root is a directory
    found_files: list[Path] = []
    if recursive:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in valid_exts:
                found_files.append(p)
    else:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in valid_exts:
                found_files.append(p)

    # Sort naturally
    found_files.sort(key=natural_sort_key)

    default_out = Path.cwd().resolve() if out_root is None else out_root

    for src_file in found_files:
        try:
            rel = src_file.relative_to(root)
        except ValueError:
            rel = Path(src_file.name)

        # Destination mirrors relative directory structure
        dst_path = default_out / rel.parent / f"{src_file.stem}.epub"
        tasks.append(
            ConversionTask(
                src_path=src_file,
                dst_path=dst_path,
                rel_path=rel,
            )
        )

    return tasks
