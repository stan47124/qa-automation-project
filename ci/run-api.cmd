@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 exit /b 2
set "runExitCode=2"
if /I "%~1"=="Prepare" goto prepare
if /I "%~1"=="Test" goto test
echo Usage: run-api.cmd Prepare or Test
goto finish

:prepare
if not defined PYTHON_EXE (
    echo ERROR: Set PYTHON_EXE to the absolute Python executable path.
    goto finish
)
"%PYTHON_EXE%" ci\check-python.py
if errorlevel 1 goto finish
if exist ".venv\Scripts\python.exe" goto dependencies
if exist ".venv" (
    echo ERROR: Incomplete .venv exists. Inspect manually; it will not be overwritten.
    goto finish
)
"%PYTHON_EXE%" -m venv .venv
if errorlevel 1 goto finish

:dependencies
".venv\Scripts\python.exe" --version
if errorlevel 1 goto finish
".venv\Scripts\python.exe" -m pip install -r requirements/api.txt
if errorlevel 1 goto finish
".venv\Scripts\python.exe" -m pip check
set "runExitCode=%ERRORLEVEL%"
goto finish

:test
if not defined REPORT_ROOT (
    echo ERROR: REPORT_ROOT must specify a new report directory.
    goto finish
)
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Workspace .venv is missing. Run Prepare first.
    goto finish
)
".venv\Scripts\python.exe" -m pytest tests/api -v --alluredir="%REPORT_ROOT%/allure-results" --junitxml="%REPORT_ROOT%/junit.xml"
set "runExitCode=%ERRORLEVEL%"

:finish
popd
exit /b %runExitCode%
