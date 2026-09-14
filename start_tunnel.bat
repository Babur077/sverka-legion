@echo off
chcp 65001 > nul
title ReconcileHub - Запуск с онлайн-доступом (Туннель)

echo ===============================================================
echo   Запуск ReconcileHub с безопасной онлайн-ссылкой для коллег
echo ===============================================================
echo.
echo Этот способ гарантированно работает, даже если:
echo - Роутер блокирует общение компьютеров (изоляция клиентов Wi-Fi);
echo - Брандмауэр Windows не пускает входящие соединения;
echo - Коллеги находятся в другом кабинете или работают удаленно.
echo.

:: Сначала запускаем сам Streamlit в фоновом окне, если он еще не запущен
echo [1/2] Проверка локального сервера...
start "ReconcileHub Server" cmd /c "python start_network.py"

timeout /t 3 >nul

echo.
echo [2/2] Создание защищенного туннеля через Cloudflare...
echo.
echo Сейчас будет сгенерирована публичная ссылка вида:
echo https://xxxx-xxxx.trycloudflare.com
echo.
echo Эту ссылку вы можете отправить любому коллеге!
echo.

where cloudflared >nul 2>nul
if %errorlevel% == 0 (
    cloudflared tunnel --url http://localhost:8501
    goto end
)

:: Пробуем через npx localtunnel если есть node.js
where npx >nul 2>nul
if %errorlevel% == 0 (
    echo [INFO] Запуск через LocalTunnel...
    npx -y localtunnel --port 8501
    goto end
)

echo [ВНИМАНИЕ] Утилита cloudflared или Node.js не обнаружена.
echo Для работы без настройки локальной сети скачайте cloudflared:
echo https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
echo и положите файл рядом с этим скриптом, переименовав в cloudflared.exe
echo.
pause

:end
