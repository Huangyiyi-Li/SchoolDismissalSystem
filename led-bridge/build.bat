@echo off
python "%~dp0..\tools\build_led_bridge.py"
exit /b %errorlevel%
