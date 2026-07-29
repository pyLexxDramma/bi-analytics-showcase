@echo off
cd /d "%~dp0"
python scripts\setup_local_ftp_env.py
if errorlevel 1 exit /b 1
cd api
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
