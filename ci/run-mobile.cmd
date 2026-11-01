@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 exit /b 2
set "runExitCode=2"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Workspace .venv is missing. Run API Prepare first.
    goto finish
)
if /I "%~1"=="Prepare" goto prepare
if /I "%~1"=="Test" goto test
if /I "%~1"=="Check" goto check
echo Usage: run-mobile.cmd Prepare, Check or Test
goto finish

:prepare
".venv\Scripts\python.exe" -m pip install -r requirements/mobile.txt
if errorlevel 1 goto finish
".venv\Scripts\python.exe" -m pip check
set "runExitCode=%ERRORLEVEL%"
goto finish

:check
".venv\Scripts\python.exe" ci/mobile_ci.py --check
set "runExitCode=%ERRORLEVEL%"
goto finish

:test
".venv\Scripts\python.exe" ci/mobile_ci.py
set "runExitCode=%ERRORLEVEL%"

:finish
popd
exit /b %runExitCode%
