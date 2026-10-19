@echo off
title PDF Studio Pro
echo ========================================================
echo Starting PDF Studio Pro (Web & Cloud PDF Editor)...
echo ========================================================

start "" http://127.0.0.1:8000
.\myenv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000

pause
