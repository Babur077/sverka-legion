@echo off
chcp 65001 > nul
title ReconcileHub - Корпоративный сервер сверок

echo ===============================================================
echo       Запуск ReconcileHub с поддержкой работы по сети
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

:: Проверяем наличие установленного streamlit
%PYTHON_BIN% -c "import streamlit" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Установка необходимых библиотек (requirements.txt)...
    %PYTHON_BIN% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости.
        pause
        exit /b 1
    )
)

echo [OK] Запуск сетевого сервера...
%PYTHON_BIN% start_network.py

if %errorlevel% neq 0 (
    echo.
    echo [ВНИМАНИЕ] Сервер завершил работу с ошибкой.
    pause
)
