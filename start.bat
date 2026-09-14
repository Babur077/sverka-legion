@echo off
chcp 65001 > nul
title Reconcile Hub Launcher

echo =======================================================
echo          Запуск платформы Reconcile Hub
echo =======================================================
echo.

:: 1. Проверяем наличие Python (python или py)
set PYTHON_CMD=
where python >nul 2>nul
if %errorlevel% == 0 (
    set PYTHON_CMD=python
) else (
    where py >nul 2>nul
    if %errorlevel% == 0 (
        set PYTHON_CMD=py
    )
)

:: 2. Если есть Python и есть сборка (папка dist или архив dist.zip)
if defined PYTHON_CMD (
    if exist "dist\index.html" goto run_python_react
    if exist "dist.zip" goto run_python_react
    if exist "app.py" (
        echo [INFO] Обнаружен Streamlit-скрипт (app.py).
    )
)

:check_node
where node >nul 2>nul
if %errorlevel% neq 0 (
    if defined PYTHON_CMD (
        goto run_python_react
    )
    echo [ОШИБКА] На вашем компьютере не найден ни Python, ни Node.js.
    echo.
    echo Установите Python: https://www.python.org/
    pause
    exit /b 1
)

if not exist "node_modules\" (
    echo [INFO] Папка node_modules не найдена. Устанавливаем зависимости...
    call npm install
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости npm.
        pause
        exit /b 1
    )
)

if not exist "dist\" (
    echo [INFO] Сборка проекта (npm run build)...
    call npm run build
)

echo.
echo [OK] Запуск React-приложения через Vite preview...
call npm run preview
goto end

:run_python_react
echo [OK] Запуск через встроенный Python-сервер (%PYTHON_CMD%)...
%PYTHON_CMD% serve_production.py
goto end

:end
pause

