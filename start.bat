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

echo Выберите вариант запуска:
echo [1] Streamlit (Рекомендуется: общая база SQLite, доступ для коллег по сети)
echo [2] React Web App (Локальный браузерный интерфейс)
echo.
set /p CHOICE="Введите 1 или 2 (по умолчанию 1): "

if "%CHOICE%"=="2" goto run_react
goto run_streamlit

:run_streamlit
call start_streamlit.bat
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
