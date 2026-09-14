@echo off
chcp 65001 > nul
title Reconcile Hub Launcher

echo =======================================================
echo          Запуск платформы Reconcile Hub
echo =======================================================
echo.

if exist "dist\index.html" (
    echo [OK] Готовая продакшен-сборка (dist) обнаружена.
    where python >nul 2>nul
    if %errorlevel% == 0 (
        echo [INFO] Запуск через встроенный Python-сервер...
        python serve_production.py
        goto end
    )
)

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] На вашем компьютере не найден ни Node.js, ни Python.
    echo.
    echo Пожалуйста, установите одно из двух:
    echo 1. Node.js с официального сайта: https://nodejs.org/ (рекомендуется LTS)
    echo    ИЛИ
    echo 2. Python 3: https://www.python.org/
    echo.
    pause
    exit /b 1
)

if not exist "node_modules\" (
    echo [INFO] Папка node_modules не найдена. Устанавливаем зависимости (это нужно 1 раз)...
    call npm install
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости npm.
        pause
        exit /b 1
    )
)

if not exist "dist\" (
    echo [INFO] Сборка продакшен-версии проекта (npm run build)...
    call npm run build
)

echo.
echo [OK] Запускаем платформу в режиме быстрого предпросмотра / продакшен...
call npm run preview

:end
pause
