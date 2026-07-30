@echo off
setlocal
cd /d "%~dp0"

if not exist "build\classes" mkdir "build\classes"
(for /r "src" %%F in (*.java) do @echo "%%F") > "build\sources.txt"

javac -encoding UTF-8 -source 8 -target 8 -cp "lib\*" -d "build\classes" @"build\sources.txt"
if errorlevel 1 exit /b 1

jar cfe "led-bridge.jar" cn.xxt.dismissal.led.OnbonLedBridge -C "build\classes" .
if errorlevel 1 exit /b 1

echo Built %CD%\led-bridge.jar
endlocal
