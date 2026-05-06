@echo off
chcp 65001 >nul
title Sistema de Planilhas Amazon - Web
cd /d "%~dp0"

echo ================================================================
echo   Sistema de Planilhas Amazon - Interface Web
echo ================================================================
echo.

REM Verifica se Python esta instalado
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado no PATH.
    pause
    exit /b 1
)

REM Verifica se Flask esta instalado, instala se faltar
python -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
    echo Instalando Flask...
    python -m pip install flask
)

REM Abre o navegador apos 2 segundos
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

echo.
echo Servidor iniciando em http://127.0.0.1:5000
echo Pressione Ctrl+C nesta janela para encerrar.
echo.

python web_app.py

pause
