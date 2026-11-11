@echo off
REM Solo la primera vez: crea la base de datos con datos de ejemplo
cd /d "%~dp0"
python -m pip install -r requirements.txt
start http://127.0.0.1:5000
python app.py --demo
pause
