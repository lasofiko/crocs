@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo CWD: %CD%
echo Python: %PY%

"%PY%" -u -m crocs %*
exit /b %ERRORLEVEL%
