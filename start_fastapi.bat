@echo off
chcp 65001 > nul
title ReconcileHub - FastAPI + React (Высокопроизводительный режим)

setlocal

echo ===============================================================
echo     ReconcileHub: FastAPI + React Web Engine
echo ===============================================================
echo.

set PYTHON_BIN=
where python >nul 2>nul
if %errorlevel% == 0 (
    set PYTHON_BIN=python
) else (
    where py >nul 2>nul
    if %errorlevel% == 0 (
        set PYTHON_BIN=py
    )
)

if not defined PYTHON_BIN (
    echo [ОШИБКА] Python не найден на вашем компьютере!
    echo Установите Python 3.10+ с сайта https://www.python.org/
    pause
    exit /b 1
)

echo [1/5] Проверка зависимостей FastAPI...
%PYTHON_BIN% -c "import fastapi, uvicorn, polars, multipart" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Доустановка библиотек FastAPI и Uvicorn...
    %PYTHON_BIN% -m pip install fastapi uvicorn python-multipart polars openpyxl fastexcel
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости FastAPI.
        pause
        exit /b 1
    )
)

echo [2/5] Проверка Node.js / npm...
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] Node.js / npm не найден.
    echo Установите Node.js, затем снова запустите start.bat.
    echo Старый dist намеренно НЕ используется, чтобы не запускать устаревший интерфейс.
    pause
    exit /b 1
)

if not exist "package.json" (
    echo [ОШИБКА] package.json не найден. Невозможно собрать React интерфейс.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo [INFO] Установка npm-зависимостей...
    call npm install
    if %errorlevel% neq 0 (
        echo [ОШИБКА] npm install завершился с ошибкой.
        pause
        exit /b 1
    )
)

echo [3/5] Удаление старого React build...
if exist "dist" rmdir /s /q "dist"

if exist "dist.zip" (
    del /q "dist.zip" >nul 2>&1
)

echo [4/5] Обязательная сборка актуального React интерфейса...
call npm run build
if %errorlevel% neq 0 (
    echo.
    echo [ОШИБКА] React build завершился с ошибкой.
    echo Сервер НЕ будет запущен с устаревшим dist.
    pause
    exit /b 1
)

if not exist "dist\index.html" (
    echo [ОШИБКА] После сборки dist\index.html не найден.
    echo Сервер НЕ будет запущен.
    pause
    exit /b 1
)

echo [OK] Актуальный React build создан.
echo.
echo [5/5] Освобождение порта 8000 и запуск FastAPI...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 4 } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo ===============================================================
echo  React + FastAPI: http://localhost:8000
echo  Swagger:         http://localhost:8000/docs
echo ===============================================================
echo.

start "" http://localhost:8000
%PYTHON_BIN% api.py

pause
endlocal
