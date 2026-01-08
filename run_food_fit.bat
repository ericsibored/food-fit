@echo off
setlocal

cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :error
)

call .venv\Scripts\activate
if errorlevel 1 goto :error

pip install -r requirements.txt
if errorlevel 1 goto :error

python app.py
if errorlevel 1 goto :error

pause
exit /b 0

:error
echo.
echo Something went wrong. Please check the output above.
pause
exit /b 1
