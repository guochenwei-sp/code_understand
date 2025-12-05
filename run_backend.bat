@echo off
cd /d "%~dp0backend"
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
pip install -r requirements.txt
) else (
    echo Warning: Virtual environment not found. Trying global python...
)
echo Starting Backend...
.\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
