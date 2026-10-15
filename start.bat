@echo off
title AnkiCraft AI - Launcher
color 0B

echo =======================================================
echo          AnkiCraft AI - Flashcard Generator
echo =======================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando entorno del Backend...
if not exist "backend\.venv" (
    echo Creando entorno virtual de Python...
    python -m venv backend\.venv
    call backend\.venv\Scripts\python -m pip install --upgrade pip
    call backend\.venv\Scripts\pip install -r backend\requirements.txt
)

echo [2/3] Iniciando Backend (http://127.0.0.1:8000)...
set "WT_EXE="
where wt.exe >nul 2>&1
if %errorlevel% equ 0 (
    set "WT_EXE=wt.exe"
) else (
    if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" (
        set "WT_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
    ) else if exist "%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\wt.exe" (
        set "WT_EXE=%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\wt.exe"
    ) else if exist "C:\Users\Manolo\AppData\Local\Microsoft\WindowsApps\wt.exe" (
        set "WT_EXE=C:\Users\Manolo\AppData\Local\Microsoft\WindowsApps\wt.exe"
    )
)

if defined WT_EXE (
    "%WT_EXE%" -w 0 nt --title "AnkiCraft AI - Backend" -d "%CD%\backend" cmd /k ".venv\Scripts\python run.py"
) else (
    start "AnkiCraft AI - Backend" cmd /k "cd backend && .venv\Scripts\python run.py"
)

echo [3/3] Iniciando Frontend de Vite (http://localhost:5173)...
timeout /t 2 /nobreak >nul
start http://localhost:5173

cd frontend
npm run dev
