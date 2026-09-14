@echo off
chcp 65001 > nul
title ReconcileHub - Запуск с онлайн-доступом (Туннель)

echo ===============================================================
echo   Запуск ReconcileHub с безопасной онлайн-ссылкой для коллег
echo ===============================================================
echo.
echo Этот способ гарантированно работает на любых компьютерах:
echo  [✓] Не требует настройки роутера (обходит изоляцию Wi-Fi клиентов);
echo  [✓] Не блокируется Брандмауэром Windows;
echo  [✓] Работает даже если коллеги в другом кабинете или дома.
echo.

:: 1. Проверяем или запускаем локальный сервер Streamlit
echo [1/3] Проверка локального сервера ReconcileHub...
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Локальный сервер не был запущен. Запускаем в фоновом окне...
    start "ReconcileHub Server" cmd /c "python start_network.py"
    timeout /t 3 >nul
) else (
    echo   [✓] Локальный сервер уже активен на порту 8501.
)

echo.
echo [2/3] Подготовка утилиты Cloudflare Tunnel...

set "CF_EXE=%~dp0cloudflared.exe"

where cloudflared >nul 2>nul
if %errorlevel% == 0 (
    set "CF_EXE=cloudflared"
)

if not exist "%CF_EXE%" if not "%CF_EXE%"=="cloudflared" (
    echo   Утилита cloudflared не найдена в папке.
    echo   Автоматическое скачивание официального cloudflared (18 МБ)...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host 'Загрузка...'; (New-Object System.Net.WebClient).DownloadFile('https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe', '%CF_EXE%')"
    if exist "%CF_EXE%" (
        echo   [✓] cloudflared успешно скачан!
    )
)

echo.
echo [3/3] Создание защищенного туннеля...
echo.
echo ===============================================================
echo  СЕЙЧАС ПОЯВИТСЯ ПУБЛИЧНАЯ ССЫЛКА ДЛЯ КОЛЛЕГ!
echo  Ищите в строках ниже ссылку вида:
echo  👉 https://xxxxx.trycloudflare.com
echo  Скопируйте её и отправьте коллегам.
echo  Для завершения работы просто закройте это окно.
echo ===============================================================
echo.

if exist "%CF_EXE%" (
    "%CF_EXE%" tunnel --url http://localhost:8501
    goto end
)
if "%CF_EXE%"=="cloudflared" (
    cloudflared tunnel --url http://localhost:8501
    goto end
)

:: Резервный вариант через встроенный OpenSSH Windows
where ssh >nul 2>nul
if %errorlevel% == 0 (
    echo [INFO] Запуск резервного туннеля через SSH...
    echo Ссылка для коллег появится ниже:
    ssh -o StrictHostKeyChecking=no -R 80:localhost:8501 nokey@localhost.run
    goto end
)

:: Резервный вариант через npx localtunnel
where npx >nul 2>nul
if %errorlevel% == 0 (
    echo [INFO] Запуск через LocalTunnel...
    npx -y localtunnel --port 8501
    goto end
)

echo [ОШИБКА] Не удалось запустить туннель автоматически.
echo Проверьте подключение к интернету или скачайте cloudflared.exe вручную:
echo https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
echo и положите в папку с программой.
echo.
pause

:end

