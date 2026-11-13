"""Tests for file collector: natural sort, directory mirroring, extension filtering."""

from pathlib import Path

import pytest
from mobi2epub.collector import collect_tasks, natural_sort_key


def test_natural_sort_key():
    filenames = ["book10.mobi", "book2.mobi", "book1.mobi", "book20.mobi"]
    sorted_files = sorted(filenames, key=natural_sort_key)
    assert sorted_files == ["book1.mobi", "book2.mobi", "book10.mobi", "book20.mobi"]


def test_collect_single_file_default_destination(tmp_path: Path):
    src = tmp_path / "novel.mobi"
    src.write_bytes(b"content")

    tasks = collect_tasks(src)
    assert len(tasks) == 1
    assert tasks[0].src_path == src.resolve()
    assert tasks[0].dst_path == tmp_path / "novel.epub"


def test_collect_single_file_custom_output_dir(tmp_path: Path):
    src = tmp_path / "novel.mobi"
    src.write_bytes(b"content")
    out_dir = tmp_path / "custom_out"

    tasks = collect_tasks(src, output_dir=out_dir)
    assert len(tasks) == 1
    assert tasks[0].dst_path == out_dir.resolve() / "novel.epub"


def test_collect_unsupported_extension_file(tmp_path: Path):
    txt_file = tmp_path / "doc.txt"
    txt_file.write_bytes(b"content")
    with pytest.raises(ValueError, match="supported extension"):
        collect_tasks(txt_file)


def test_collect_nonexistent_path(tmp_path: Path):
    missing = tmp_path / "missing.mobi"
    with pytest.raises(FileNotFoundError):
        collect_tasks(missing)


def test_collect_folder_flat_and_sorted(tmp_path: Path):
    (tmp_path / "b10.mobi").write_bytes(b"data")
    (tmp_path / "b2.mobi").write_bytes(b"data")
    (tmp_path / "b1.mobi").write_bytes(b"data")
    (tmp_path / "ignore.pdf").write_bytes(b"data")

    out_dir = tmp_path / "out"
    tasks = collect_tasks(tmp_path, output_dir=out_dir, recursive=False)

    assert len(tasks) == 3
    # Check natural order
    names = [t.src_path.name for t in tasks]
    assert names == ["b1.mobi", "b2.mobi", "b10.mobi"]
    # Check destination names
    dst_names = [t.dst_path.name for t in tasks]
    assert dst_names == ["b1.epub", "b2.epub", "b10.epub"]


def test_collect_folder_recursive_mirroring(tmp_path: Path):
    sub1 = tmp_path / "author1"
    sub1.mkdir()
    (sub1 / "book1.mobi").write_bytes(b"data")

    sub2 = tmp_path / "author2" / "series"
    sub2.mkdir(parents=True)
    (sub2 / "book2.mobi").write_bytes(b"data")

    out_dir = tmp_path / "output"
    tasks = collect_tasks(tmp_path, output_dir=out_dir, recursive=True)

    assert len(tasks) == 2
    task1 = next(t for t in tasks if t.src_path.name == "book1.mobi")
    task2 = next(t for t in tasks if t.src_path.name == "book2.mobi")

    assert task1.dst_path == out_dir.resolve() / "author1" / "book1.epub"
    assert task2.dst_path == out_dir.resolve() / "author2" / "series" / "book2.epub"
