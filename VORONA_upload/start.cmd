@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
chcp 65001 >nul

set "VORONA_PYTHON=python"
python -c "import sys" >nul 2>&1
if not errorlevel 1 goto check_dependencies
set "VORONA_PYTHON=py -3"
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 goto check_dependencies
echo ERROR: Python 3 was not found. Install Python and try again.
pause
exit /b 1

:check_dependencies
%VORONA_PYTHON% -c "import flask, pandas, sqlalchemy, psycopg2, openpyxl, xlrd"
if not errorlevel 1 goto start_app
echo.
echo ERROR: Required Python packages are missing. Install them with:
echo %VORONA_PYTHON% -m pip install Flask pandas SQLAlchemy psycopg2-binary openpyxl xlrd
pause
exit /b 1

:start_app
echo Starting VORONA from "%CD%"...
echo Open http://127.0.0.1:5000 after the server starts.
echo Keep this window open while using VORONA. Press Ctrl+C to stop.
echo.
%VORONA_PYTHON% app.py
set "VORONA_EXIT_CODE=%ERRORLEVEL%"
echo.
if "%VORONA_EXIT_CODE%"=="0" goto stopped
echo VORONA could not start or stopped with an error.
echo Check the message above and make sure the PostgreSQL database is running.
:stopped
pause
exit /b %VORONA_EXIT_CODE%
