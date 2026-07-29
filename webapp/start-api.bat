@echo off
cd /d "%~dp0api"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
