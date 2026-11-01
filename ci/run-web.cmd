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
echo Usage: run-web.cmd Prepare or Test
goto finish

:prepare
".venv\Scripts\python.exe" -m pip install -r requirements/ui.txt
if errorlevel 1 goto finish
".venv\Scripts\python.exe" -m pip check
set "runExitCode=%ERRORLEVEL%"
goto finish

:test
if not defined REPORT_ROOT (
    echo ERROR: REPORT_ROOT must specify a new Web UI report directory.
    goto finish
)
".venv\Scripts\python.exe" -m pytest tests/ui -v --basetemp="%REPORT_ROOT%/pytest-tmp" --alluredir="%REPORT_ROOT%/allure-results" --junitxml="%REPORT_ROOT%/junit.xml"
set "runExitCode=%ERRORLEVEL%"

:finish
popd
exit /b %runExitCode%
