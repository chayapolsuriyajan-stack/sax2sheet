@echo off
REM Double-click launcher for sax2sheet over HTTPS on your local network,
REM so it's reachable from an iPad/phone on the same wifi. Mic access on
REM iOS Safari requires HTTPS (or localhost), which is why this uses a
REM self-signed cert instead of plain HTTP.
cd /d "%~dp0"

if not exist "certs\dev-cert.pem" (
  echo Missing certs\dev-cert.pem / dev-key.pem.
  echo Generate them first ^(see README.md "Access from iPad/phone"^).
  pause
  exit /b 1
)

echo Starting sax2sheet server on your local network...
start "sax2sheet server (LAN/HTTPS)" cmd /k "uv run uvicorn sax2sheet.api.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile certs\dev-key.pem --ssl-certfile certs\dev-cert.pem --reload"

timeout /t 3 /nobreak >nul
echo.
echo On this PC:      https://localhost:8443
echo On iPad/phone:   https://192.168.68.85:8443
echo ^(same wifi network required^)
echo.
echo Your browser will warn "not secure" the first time -- that's expected
echo for a self-signed cert. Tap Advanced / Visit anyway to continue.
echo.
start "" "https://localhost:8443"
