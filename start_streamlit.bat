@echo off
chcp 65001 > nul
title ReconcileHub - Streamlit Server
echo ===============================================================
echo       Запуск ReconcileHub с поддержкой совместной работы
echo ===============================================================
echo.

where python >nul 2>nul
if %errorlevel% == 0 (
    python start_network.py
    goto end
)

where py >nul 2>nul
if %errorlevel% == 0 (
    py start_network.py
    goto end
)

echo [ОШИБКА] Python не найден! Установите Python с сайта https://python.org
pause

:end
