@echo off
chcp 65001 > nul
title Диагностика сети ReconcileHub

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
    echo [ОШИБКА] Python не найден на компьютере!
    pause
    exit /b 1
)

%PYTHON_BIN% check_network.py
echo.
pause
