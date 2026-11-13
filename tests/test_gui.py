"""Smoke test for Tkinter GUI: builds the window without showing it."""

import tkinter as tk
from pathlib import Path

import pytest
from mobi2epub.gui import MobiToEpubApp


def test_gui_smoke_init(tmp_path: Path):
    try:
        root = tk.Tk()
    except Exception as e:
        pytest.skip(f"Tkinter display not available: {e}")

    root.withdraw()  # Hide window

    try:
        app = MobiToEpubApp(root)

        # Initial button states
        assert "disabled" in app.btn_convert.state()
        assert "disabled" in app.btn_cancel.state()
        assert "disabled" in app.btn_open_folder.state()

        # Check options default values
        assert app.var_recursive.get() is True
        assert app.var_force.get() is False

        # Simulate setting input and writable output
        sample = Path("tests/fixtures/sample_mobi6.mobi")
        if sample.exists():
            app.selected_inputs = [sample]
            app.var_input_text.set(str(sample))

        app.var_output_text.set(str(tmp_path))
        app._update_convert_button_state()

        # Convert button should now be enabled
        if sample.exists():
            assert "disabled" not in app.btn_convert.state()

        # Test log append and clear
        app._append_log("Test log entry", "info")
        content = app.txt_log.get("1.0", tk.END)
        assert "Test log entry" in content
        app._clear_log()
        assert app.txt_log.get("1.0", tk.END).strip() == ""

    finally:
        root.destroy()
