@echo off
REM Batch file to run the SmartCorr script for INFERENCE
REM This script is intended to be run by the Datacore orchestrator

REM Run the Python script with arguments (Datacore will append its own arguments)
py run_inference.py %*

pause
