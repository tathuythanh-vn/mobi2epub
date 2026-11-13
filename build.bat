@echo off
setlocal enabledelayedexpansion

echo =======================================================
echo Building MobiToEpub (Window) and mobi2epub (CLI)
echo =======================================================

:: Locate python
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python not found. Please install Python 3.10+ or set up .venv.
        exit /b 1
    )
)

echo [1/3] Checking requirements and installing dependencies...
%PYTHON_EXE% -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

echo [2/3] Running PyInstaller with mobi2epub.spec...
%PYTHON_EXE% -m PyInstaller mobi2epub.spec --clean --noconfirm
if !errorlevel! neq 0 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

echo [3/3] Checking built executables in dist\...
if exist "dist\MobiToEpub.exe" (
    for %%F in ("dist\MobiToEpub.exe") do (
        set /a size_mb=%%~zF / 1048576
        echo  - dist\MobiToEpub.exe : %%~zF bytes - ~!size_mb! MB - Window GUI
    )
) else (
    echo [ERROR] dist\MobiToEpub.exe was not created!
    exit /b 1
)

if exist "dist\mobi2epub.exe" (
    for %%F in ("dist\mobi2epub.exe") do (
        set /a size_mb=%%~zF / 1048576
        echo  - dist\mobi2epub.exe  : %%~zF bytes - ~!size_mb! MB - Console CLI
    )
)

echo.
echo =======================================================
echo Build complete!
echo Ready for distribution: dist\MobiToEpub.exe
echo =======================================================
