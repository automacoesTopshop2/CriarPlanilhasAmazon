@echo off
chcp 65001 >nul 2>&1
title Sistema de Planilhas Amazon

echo ============================================
echo   Sistema de Planilhas Amazon - Iniciando
echo ============================================
echo.

:: Verifica se o Python está instalado
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado!
    echo.
    echo Instale o Python em: https://www.python.org/downloads/
    echo IMPORTANTE: Marque "Add Python to PATH" na instalacao.
    echo.
    pause
    exit /b 1
)

echo [OK] Python encontrado.

:: Verifica e instala dependencias
echo.
echo Verificando dependencias...

python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INSTALANDO] streamlit...
    pip install streamlit --quiet
)

python -c "import openpyxl" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INSTALANDO] openpyxl...
    pip install openpyxl --quiet
)

python -c "import pandas" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INSTALANDO] pandas...
    pip install pandas --quiet
)

python -c "import dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INSTALANDO] python-dotenv...
    pip install python-dotenv --quiet
)

echo [OK] Todas as dependencias instaladas.
echo.

:: Inicia o Streamlit
echo Iniciando o sistema... O navegador vai abrir automaticamente.
echo Para encerrar, feche esta janela ou pressione Ctrl+C.
echo.

cd /d "%~dp0"
python -m streamlit run app.py
pause
