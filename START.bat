@echo off
title ExamTrack - Launcher
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo.
  echo ExamTrack could not start. Read the message above.
  pause
)
