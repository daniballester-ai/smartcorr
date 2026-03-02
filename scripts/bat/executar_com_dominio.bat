@echo off
REM ============================================================
REM Script para executar Python com credenciais de dominio TPB
REM Autor: SmartCorr Team
REM ============================================================

setlocal enabledelayedexpansion

REM Configuracoes
set "DOMINIO=tpb"
set "USUARIO=ballester.19"
set "PASTA_PROJETO=c:\TP_ML\BI_Ferramenta_Correlacao_Inteligente\SmartCorr"
set "PYTHON_VENV=%PASTA_PROJETO%\venv\Scripts\python.exe"

REM Verifica se foi passado um script como argumento
if "%~1"=="" (
    echo.
    echo ============================================================
    echo   EXECUTAR SCRIPT PYTHON COM CREDENCIAIS DE DOMINIO
    echo ============================================================
    echo.
    echo Uso: %~nx0 [nome_do_script.py]
    echo.
    echo Scripts disponiveis:
    echo.
    for %%f in ("%PASTA_PROJETO%\*.py") do echo   - %%~nxf
    echo.
    echo Exemplo: %~nx0 teste_leitura_banco.py
    echo.
    pause
    exit /b 1
)

REM Verifica se o arquivo existe
if not exist "%PASTA_PROJETO%\%~1" (
    echo.
    echo ERRO: Arquivo "%~1" nao encontrado em %PASTA_PROJETO%
    echo.
    pause
    exit /b 1
)

echo.
echo Executando %~1 com credenciais de dominio %DOMINIO%\%USUARIO%...
echo.

runas /netonly /user:%DOMINIO%\%USUARIO% "cmd /c cd /d %PASTA_PROJETO% && %PYTHON_VENV% %~1 && pause"

echo.
echo Script iniciado em nova janela.
