@echo off
call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --reload
pause
