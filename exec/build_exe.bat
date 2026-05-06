@echo off
REM ============================================================================
REM  Empacota o app desktop como .exe usando PyInstaller (modo onefile)
REM ============================================================================
REM  Requisitos:
REM   - Python e o ambiente virtual configurados (.venv)
REM   - Dependencias instaladas: pip install -r requirements.txt
REM
REM  Saida:
REM   - dist\PlanilhasAmazon.exe   (executavel auto-contido)
REM ============================================================================

setlocal
cd /d "%~dp0"

if exist "..\\.venv\Scripts\python.exe" (
    set "PY=..\\.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo.
echo === Limpando builds anteriores ===
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "PlanilhasAmazon.spec" del /q "PlanilhasAmazon.spec"

echo.
echo === Empacotando com PyInstaller ===
"%PY%" -m PyInstaller ^
    --noconsole ^
    --onefile ^
    --name "PlanilhasAmazon" ^
    --icon "NONE" ^
    --collect-all customtkinter ^
    --hidden-import openpyxl ^
    --hidden-import pandas ^
    --paths ".." ^
    app_desktop.py

if errorlevel 1 (
    echo.
    echo *** Falha no empacotamento ***
    pause
    exit /b 1
)

echo.
echo === Build concluido ===
echo Executavel: dist\PlanilhasAmazon.exe
echo.
pause
endlocal
