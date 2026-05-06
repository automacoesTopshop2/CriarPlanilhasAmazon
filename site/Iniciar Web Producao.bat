@echo off
chcp 65001 >nul
title Topshop Amazon - Producao (waitress)
cd /d "%~dp0"

REM ============================================================
REM PRODUCAO - Servidor WSGI com waitress
REM ============================================================
REM IMPORTANTE: Single-process + multi-threads (SEM --processes >1)
REM
REM O rate limiter usa storage em memoria. Se voce subir
REM multiplos processos, cada processo tera seu proprio
REM contador, e brute-force passa a aceitar N x limite por IP.
REM
REM Para escalar para multi-processo, configure Redis em
REM web_app.py (storage_uri="redis://...") antes de aumentar
REM o numero de processos.
REM ============================================================

REM Carrega .env (ENV=production)
set ENV=production
set SESSION_COOKIE_SECURE=1

REM Verifica SECRET_KEY
python -c "import os; assert os.getenv('SECRET_KEY'), 'Defina SECRET_KEY no .env'" 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] SECRET_KEY nao definida. Edite o .env.
    pause
    exit /b 1
)

REM Verifica waitress
python -c "import waitress" 2>nul
if %errorlevel% neq 0 (
    echo Instalando waitress...
    python -m pip install waitress
)

echo.
echo ================================================================
echo   Topshop Amazon System - PRODUCAO (waitress)
echo ================================================================
echo   Endereco: http://127.0.0.1:5000
echo   Modo:     single-process, 8 threads
echo ================================================================
echo.

python -m waitress --threads=8 --listen=127.0.0.1:5000 web_app:app

pause
