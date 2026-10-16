@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
    if not errorlevel 1 (
        python server.py --open
        if errorlevel 1 pause
        exit /b
    )
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
    if not errorlevel 1 (
        py -3 server.py --open
        if errorlevel 1 pause
        exit /b
    )
)
echo Python 3.10 or later is required. Download it from https://www.python.org/downloads/
pause
