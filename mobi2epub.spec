# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

mobi_datas, mobi_binaries, mobi_hiddenimports = collect_all('mobi')
bs4_datas, bs4_binaries, bs4_hiddenimports = collect_all('bs4')

common_datas = [('app_icon.ico', '.')] + mobi_datas + bs4_datas
common_binaries = mobi_binaries + bs4_binaries
common_hiddenimports = mobi_hiddenimports + bs4_hiddenimports + [
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'bs4',
    'soupsieve',
    'loguru',
    'win32_setctime',
]

# ---------------------------------------------------------------------------
# Target 1: MobiToEpub.exe (Windowed GUI)
# ---------------------------------------------------------------------------
a_gui = Analysis(
    ['gui_main.py'],
    pathex=['.'],
    binaries=common_binaries,
    datas=common_datas,
    hiddenimports=common_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    a_gui.binaries,
    a_gui.datas,
    [],
    name='MobiToEpub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)

# ---------------------------------------------------------------------------
# Target 2: mobi2epub.exe (Console CLI)
# ---------------------------------------------------------------------------
a_cli = Analysis(
    ['cli_main.py'],
    pathex=['.'],
    binaries=common_binaries,
    datas=common_datas,
    hiddenimports=common_hiddenimports + ['tqdm'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.datas,
    [],
    name='mobi2epub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
