"""Tests for mobi2epub runner: events, cancellation, and in-process execution."""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from mobi2epub.runner import (
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


def test_runner_events_success(tmp_path: Path):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    events: list[RunnerEvent] = []
    options = RunnerOptions(force=True, jobs=1)
    summary = run_batch(
        inputs=sample,
        out_dir=tmp_path,
        options=options,
        on_event=events.append,
    )

    assert not summary.cancelled
    assert len(summary.converted) == 1
    assert len(summary.failed) == 0

    types = [type(e) for e in events]
    assert types == [Started, FileStarted, FileDone, Finished]
    assert events[0].total == 1
    assert events[1].name == "sample_mobi6.mobi"
    assert events[2].dst_path == tmp_path / "sample_mobi6.epub"


def test_runner_events_skip(tmp_path: Path):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    dst = tmp_path / "sample_mobi6.epub"
    dst.write_bytes(b"dummy existing")

    events: list[RunnerEvent] = []
    options = RunnerOptions(force=False, jobs=1)
    summary = run_batch(
        inputs=sample,
        out_dir=tmp_path,
        options=options,
        on_event=events.append,
    )

    assert not summary.cancelled
    assert len(summary.converted) == 0
    assert len(summary.skipped) == 1

    types = [type(e) for e in events]
    assert types == [Started, FileStarted, FileSkipped, Finished]
    assert "already exists" in events[2].reason.lower()


def test_runner_events_failed(tmp_path: Path):
    corrupt = Path("tests/fixtures/corrupt.mobi")
    if not corrupt.exists():
        pytest.skip("corrupt.mobi not available")

    events: list[RunnerEvent] = []
    options = RunnerOptions(force=True, jobs=1)
    summary = run_batch(
        inputs=corrupt,
        out_dir=tmp_path,
        options=options,
        on_event=events.append,
    )

    assert len(summary.failed) == 1
    types = [type(e) for e in events]
    assert types == [Started, FileStarted, FileFailed, Finished]
    assert events[2].error_type == "corrupt"


def test_runner_cancel(tmp_path: Path):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    cancel_evt = threading.Event()
    cancel_evt.set()  # Cancel immediately before processing

    events: list[RunnerEvent] = []
    options = RunnerOptions(force=True, jobs=1)
    summary = run_batch(
        inputs=sample,
        out_dir=tmp_path,
        options=options,
        on_event=events.append,
        cancel_event=cancel_evt,
    )

    assert summary.cancelled
    types = [type(e) for e in events]
    assert Cancelled in types


def test_runner_jobs_1_never_spawns_process_pool(tmp_path: Path):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    with patch("mobi2epub.runner.ProcessPoolExecutor") as mock_pool:
        options = RunnerOptions(force=True, jobs=1)
        run_batch(
            inputs=sample,
            out_dir=tmp_path,
            options=options,
        )
        mock_pool.assert_not_called()


def test_runner_multiple_files_input(tmp_path: Path):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    f1 = tmp_path / "book_a.mobi"
    f2 = tmp_path / "book_b.mobi"
    f1.write_bytes(sample.read_bytes())
    f2.write_bytes(sample.read_bytes())

    out_dir = tmp_path / "out"
    options = RunnerOptions(force=True, jobs=1)
    summary = run_batch(
        inputs=[f1, f2],
        out_dir=out_dir,
        options=options,
    )

    assert summary.total == 2
    assert len(summary.converted) == 2
    assert (out_dir / "book_a.epub").exists()
    assert (out_dir / "book_b.epub").exists()
