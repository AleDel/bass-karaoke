@echo off
rem Bass Karaoke - arranque en desarrollo
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bass_karaoke_v3.py %*
) else (
    python bass_karaoke_v3.py %*
)
if errorlevel 1 pause
