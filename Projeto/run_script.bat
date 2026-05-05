@echo off
REM Batch file to run the AbsenteeismPredictor script WITHOUT evaluation

@REM REM Activate the virtual environment
@REM call .venv\Scripts\activate.bat

REM Run the Python script with arguments (without --evaluate_model)
py main.py --InitialDateCtrl  "2026-04-04 00:00:00.000" --FinalDateCtrl "2026-04-04 08:00:00.000"  --dias_atras 90 --dias_frente 15 --ProcessTable "[dbo].[stageProcessoAbsenteismoPredicao]" --ProcessKey "99" --connectionString "DRIVER=SQL Server;SERVER=localhost;DATABASE=dbAbs;UID=sa;PWD=Absenteismo@2026!;TrustServerCertificate=yes;Application Name=DEV - ABS GUARD BI;"

@REM REM Deactivate the virtual environment (optional)

PAUSE