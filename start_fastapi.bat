@echo off
chcp 65001 > nul
title ReconcileHub - FastAPI + React (Высокопроизводительный режим)

echo ===============================================================
echo     ReconcileHub: Запуск FastAPI + React Web Engine
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

echo [1/4] Проверка зависимостей FastAPI...
%PYTHON_BIN% -c "import fastapi, uvicorn, polars, multipart" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Доустановка библиотек FastAPI и Uvicorn...
    %PYTHON_BIN% -m pip install fastapi uvicorn python-multipart polars openpyxl fastexcel
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить библиотеки.
        pause
        exit /b 1
    )
)

echo [2/4] Проверка и сборка React...
where npm >nul 2>nul
if %errorlevel% == 0 (
    if not exist "node_modules" (
        echo [INFO] Установка npm-зависимостей...
        call npm install
        if %errorlevel% neq 0 echo [ВНИМАНИЕ] npm install завершился с ошибкой.
    )
    if exist "package.json" (
        echo [INFO] Сборка актуального React интерфейса...
        call npm run build
        if %errorlevel% neq 0 echo [ВНИМАНИЕ] Сборка React не удалась. Будет использован существующий dist.
    )
) else (
    echo [ВНИМАНИЕ] Node/npm не найден. Проверяю готовый dist/dist.zip...
)

if not exist "dist" (
    if exist "dist.zip" (
        echo [INFO] Распаковка готового интерфейса React из dist.zip...
        %PYTHON_BIN% -c "import zipfile; zipfile.ZipFile('dist.zip', 'r').extractall('.')"
    )
)

if not exist "dist" (
    echo [ОШИБКА] React dist не найден. Установите Node.js и выполните npm run build.
    pause
    exit /b 1
)

echo [3/4] Освобождение порта 8000 от старых процессов...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 4 } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [4/4] Запуск сервера FastAPI + React на порту 8000...
echo.
echo ===============================================================
echo  Интерфейс React и API запускаются по адресу:
echo    Локально:             http://localhost:8000
echo    Документация Swagger: http://localhost:8000/docs
echo ===============================================================
echo.

start "" http://localhost:8000
%PYTHON_BIN% api.py

pause
