@echo off
chcp 65001 > nul
title ReconcileHub

echo ===============================================================
echo           ReconcileHub - FastAPI + React
echo ===============================================================
echo.

set PYTHON_BIN=
where python >nul 2>nul
if %errorlevel% == 0 (
    set PYTHON_BIN=python
) else (
    where py >nul 2>nul
    if %errorlevel% == 0 set PYTHON_BIN=py
)

if not defined PYTHON_BIN (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+.
    pause
    exit /b 1
)

where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] Node.js/npm не найден. Установите Node.js.
    pause
    exit /b 1
)

echo [1/3] Python зависимости...
%PYTHON_BIN% -c "import fastapi, uvicorn, polars, pandas" >nul 2>nul
if %errorlevel% neq 0 (
    %PYTHON_BIN% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить Python зависимости.
        pause
        exit /b 1
    )
)

echo [2/3] React зависимости и production build...
if not exist "node_modules" (
    call npm ci --no-audit --no-fund
    if %errorlevel% neq 0 (
        echo [ОШИБКА] npm ci завершился с ошибкой.
        pause
        exit /b 1
    )
)

call npm run build
if %errorlevel% neq 0 (
    echo [ОШИБКА] React build завершился с ошибкой.
    pause
    exit /b 1
)

echo [3/3] Запуск ReconcileHub...
echo.
echo   http://localhost:8000
echo   Swagger: http://localhost:8000/docs
echo.
start "" http://localhost:8000
%PYTHON_BIN% api.py

pause
