@echo off
cd /d "%~dp0"
echo Rodando tuning robusto (paralelo, ~ min)...
.venv\Scripts\python.exe -u run_tuning_robusto.py --paralelo
pause
