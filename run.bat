@echo off
cd /d "%~dp0"

if not exist config.json (
    echo Missing config.json.
    pause
    exit /b 1
)

python -c "import telegram" >nul 2>&1
if errorlevel 1 (
    echo Missing dependency. Run: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

python main.py
if errorlevel 1 pause
