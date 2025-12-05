@echo off
cd /d "%~dp0frontend"
echo Starting Frontend (Electron + React)...
npm run electron:dev
pause
