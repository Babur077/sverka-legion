@echo off
chcp 65001 > nul
title ReconcileHub - Онлайн-доступ для коллег
cls

echo ===============================================================
echo   Запуск ReconcileHub с безопасной онлайн-ссылкой для коллег
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
    echo Установите Python с https://www.python.org/ и отметьте "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

%PYTHON_BIN% start_tunnel.py

echo.
echo ===============================================================
echo  Работа туннеля завершена.
echo ===============================================================
pause


