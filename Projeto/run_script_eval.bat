@echo off
REM Batch file to run the AbsenteeismPredictor script with expected arguments

@REM REM Activate the virtual environment
@REM call .venv\Scripts\activate.bat

REM Run the Python script with arguments
py main.py --InitialDateCtrl "2026-04-04 00:00:00.000" --FinalDateCtrl "2026-04-04 08:00:00.000" --dias_atras 90 --dias_frente 15 --ProcessTable "[dbo].[stageProcessoAbsenteismoPredicao]" --ProcessKey "99" --connectionString "DRIVER=SQL Server;SERVER=localhost;DATABASE=dbAbs;UID=sa;PWD=Absenteismo@2026!;TrustServerCertificate=yes;Application Name=DEV - ABS GUARD BI;" --evaluate_model

@REM REM Deactivate the virtual environment (optional)
@REM call deactivate

pause