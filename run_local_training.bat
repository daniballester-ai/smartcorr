@echo off
echo ========================================================
echo   Executando SmartCorr - TREINAMENTO (Ambiente Local)
echo ========================================================
echo.

REM ATENCAO: Substitua "seu_usuario" e "sua_senha" pelas credenciais reais do SQL Server 
REM utilizadas no Datacore para acessar o servidor SPWS-VM-DB81.
set DB_CONNECTION_STRING=DRIVER={SQL Server};SERVER=SPWS-VM-DB81;DATABASE=OdsCorp;UID=seu_usuario;PWD=sua_senha

echo Conectando ao banco de dados com SQL Authentication...
echo.

REM Executa o pipeline de treinamento
py run_training.py

echo.
pause
