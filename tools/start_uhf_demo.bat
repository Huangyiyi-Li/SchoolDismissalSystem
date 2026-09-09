@echo off
cd /d "%~dp0.."
py -3 tools\uhf_demo.py
if errorlevel 1 pause
