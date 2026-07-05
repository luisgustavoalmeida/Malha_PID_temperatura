@echo off
cd /d "%~dp0"
echo Rodando simulacao...
.venv\Scripts\python.exe -u run_simulation.py
echo.
echo Graficos em saida_simulacao\
pause
