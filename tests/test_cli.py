"""Tests for CLI arguments, exit codes, and end-to-end flows."""

from pathlib import Path

import pytest
from mobi2epub.cli import main


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Convert MOBI books to standard EPUB files" in captured.out


def test_cli_missing_input_exit_code_2(capsys):
    code = main(["non_existent_path.mobi"])
    assert code == 2
    captured = capsys.readouterr()
    assert "does not exist" in captured.err


def test_cli_empty_folder_exit_code_2(tmp_path: Path, capsys):
    code = main([str(tmp_path)])
    assert code == 2
    captured = capsys.readouterr()
    assert "No .mobi files found" in captured.err


def test_cli_successful_conversion(tmp_path: Path, capsys):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    out_file = tmp_path / "sample_mobi6.epub"
    code = main([str(sample), "-o", str(tmp_path), "--force"])
    assert code == 0
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_cli_skip_without_force(tmp_path: Path, capsys):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    out_file = tmp_path / "sample_mobi6.epub"
    out_file.write_bytes(b"dummy existing")

    code = main([str(sample), "-o", str(tmp_path)])
    assert code == 0  # Skipped is not a failure, exit 0
    assert out_file.read_bytes() == b"dummy existing"
    captured = capsys.readouterr()
    assert "Skipped: 1" in captured.out


def test_cli_corrupt_file_exit_code_1(tmp_path: Path, capsys):
    corrupt = tmp_path / "corrupt.mobi"
    corrupt.write_bytes(b"not a mobi")

    code = main([str(corrupt), "-o", str(tmp_path), "--force"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Failed: 1" in captured.out
    assert "CORRUPT" in captured.out


def test_cli_quiet_mode_suppresses_summary(tmp_path: Path, capsys):
    sample = Path("tests/fixtures/sample_mobi6.mobi")
    if not sample.exists():
        pytest.skip("sample_mobi6.mobi not available")

    code = main([str(sample), "-o", str(tmp_path), "--force", "--quiet"])
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
