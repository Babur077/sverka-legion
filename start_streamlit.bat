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

:: Проверяем наличие всех необходимых библиотек
echo [1/3] Проверка библиотек (Streamlit, Pandas, Polars, OpenPyXL, Plotly)...
%PYTHON_BIN% -c "import streamlit, pandas, polars, openpyxl, plotly" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Установка или обновление библиотек из requirements.txt...
    %PYTHON_BIN% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось автоматически установить библиотеки.
        echo Попробуйте вручную выполнить команду в консоли:
        echo   %PYTHON_BIN% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo [2/3] Освобождение порта 8501 от старых процессов...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 4 } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [3/3] Запуск сетевого сервера ReconcileHub...
echo.

%PYTHON_BIN% start_network.py

if %errorlevel% neq 0 (
    echo.
    echo ===============================================================
    echo [ВНИМАНИЕ] Сервер завершил работу с кодом ошибки %errorlevel%.
    echo ===============================================================
    echo Запуск прямого режима Streamlit...
    %PYTHON_BIN% -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
)

echo.
echo ===============================================================
echo  Сервер ReconcileHub остановлен.
echo ===============================================================
pause
