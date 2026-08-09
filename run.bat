@echo off
REM Double-click launcher for sax2sheet: starts the server in its own
REM window and opens the app in your default browser.
cd /d "%~dp0"

echo Starting sax2sheet server...
start "sax2sheet server" cmd /k "uv run uvicorn sax2sheet.api.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000"
