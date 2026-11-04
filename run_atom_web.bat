@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ATOM-Web] Virtual environment not found. Run setup first:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)
echo Starting ATOM-Web on http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" -m src.main
