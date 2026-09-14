@echo off
chcp 65001 > nul
title Reconcile Hub Launcher

echo =======================================================
echo          Запуск платформы Reconcile Hub
echo =======================================================
echo.

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

if not defined PYTHON_CMD (
    echo [ОШИБКА] Python не найден на вашем компьютере.
    echo Пожалуйста, установите Python с https://www.python.org/
    pause
    exit /b 1
)

echo Выберите действие:
echo [1] Запуск ReconcileHub (по локальной сети Wi-Fi / Офис)
echo [2] Запуск через интернет-ссылку (Cloudflare Туннель — РЕКОМЕНДУЕТСЯ, если не пускает роутер)
echo [3] Авто-настройка Брандмауэра Windows (открыть порт 8501)
echo [4] Диагностика сети (проверить почему не подключаются коллеги)
echo [5] React Web App (локальный браузерный интерфейс)
echo.
set /p CHOICE="Введите номер действия (1-5, по умолчанию 1): "

if "%CHOICE%"=="2" goto run_tunnel
if "%CHOICE%"=="3" goto run_firewall
if "%CHOICE%"=="4" goto run_diag
if "%CHOICE%"=="5" goto run_react
goto run_streamlit

:run_streamlit
call start_streamlit.bat
goto end

:run_tunnel
call start_tunnel.bat
goto end

:run_firewall
call allow_firewall.bat
goto end

:run_diag
call check_network.bat
goto end

:run_react
if exist "serve_production.py" (
    echo.
    echo [OK] Запуск React приложения...
    %PYTHON_CMD% serve_production.py
    goto end
)
where node >nul 2>nul
if %errorlevel% == 0 (
    npm run dev
    goto end
)
echo [ОШИБКА] Не удалось запустить React.
pause

:end
