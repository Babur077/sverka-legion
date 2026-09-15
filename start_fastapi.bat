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
    echo При установке обязательно отметьте галочку "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

:: Проверяем наличие FastAPI, Uvicorn и Polars
echo [1/2] Проверка зависимостей (FastAPI, Uvicorn, Polars)...
%PYTHON_BIN% -c "import fastapi, uvicorn, polars, multipart" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Доустановка библиотек FastAPI и Uvicorn...
    %PYTHON_BIN% -m pip install fastapi uvicorn python-multipart polars openpyxl fastexcel
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить библиотеки.
        echo Попробуйте вручную выполнить: pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

:: Распаковываем dist.zip, если папки dist еще нет
if not exist "dist" (
    if exist "dist.zip" (
        echo [INFO] Распаковка готового интерфейса React из dist.zip...
        %PYTHON_BIN% -c "import zipfile, os; zipfile.ZipFile('dist.zip', 'r').extractall('.')"
    )
)

echo [2/3] Освобождение порта 8000 от старых процессов...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 4 } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [3/3] Запуск сервера FastAPI + React на порту 8000...
echo.
echo ===============================================================
echo  Интерфейс React и API запускаются по адресу:
echo    Локально:             http://localhost:8000
echo    Документация Swagger: http://localhost:8000/docs
echo ===============================================================
echo.

:: Автоматическое открытие в браузере
start "" http://localhost:8000

%PYTHON_BIN% api.py

pause
