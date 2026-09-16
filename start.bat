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

echo ВЫБЕРИТЕ РЕЖИМ РАБОТЫ:
echo.
echo  [1] Локальная сеть (Streamlit legacy)
echo      --^> Старый интерфейс Streamlit на порту 8501.
echo.
echo  [2] Онлайн-ссылка для удаленных коллег (Cloudflare / Pinggy Туннель)
echo  [3] Настройка Брандмауэра Windows (открыть порты 8501, 3000, 8000)
echo  [4] Диагностика сети (проверить подключение коллег)
echo  [5] React Web App (автономный браузерный интерфейс)
echo  [6] FastAPI + React (текущий основной интерфейс) [ПО УМОЛЧАНИЮ]
echo.
set /p CHOICE="Введите номер действия (1-6, по умолчанию 6 - FastAPI + React): "

if "%CHOICE%"=="" set CHOICE=6
if "%CHOICE%"=="1" goto run_streamlit
if "%CHOICE%"=="2" goto run_tunnel
if "%CHOICE%"=="3" goto run_firewall
if "%CHOICE%"=="4" goto run_diag
if "%CHOICE%"=="5" goto run_react
if "%CHOICE%"=="6" goto run_fastapi
goto run_fastapi

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
goto end

:run_fastapi
if exist "start_fastapi.bat" (
    call start_fastapi.bat
    goto end
)
if exist "api.py" (
    %PYTHON_CMD% api.py
    goto end
)
echo [ОШИБКА] Файл api.py не найден.
pause
goto end

:end
echo.
echo =======================================================
echo     Работа программы завершена.
echo =======================================================
pause
