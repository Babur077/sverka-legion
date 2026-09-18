@echo off
chcp 65001 > nul
title Настройка Брандмауэра Windows для ReconcileHub

echo =================================================================
echo       Разрешение сетевого доступа к ReconcileHub в Брандмауэре
echo =================================================================
echo.

:: 1. Автоматический запрос прав Администратора через UAC при обычном запуске
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Запрос прав Администратора...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo [✓] Запущено с правами Администратора.
echo.

:: 2. Поиск реального пути к python.exe на компьютере
set "REAL_PY="
for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined REAL_PY set "REAL_PY=%%I"
)
if not defined REAL_PY (
    for /f "delims=" %%I in ('where py 2^>nul') do (
        if not defined REAL_PY set "REAL_PY=%%I"
    )
)

echo [1/4] Удаление старых или блокирующих правил...
netsh advfirewall firewall delete rule name="ReconcileHub Port 8501" >nul 2>&1
netsh advfirewall firewall delete rule name="ReconcileHub Port 3000" >nul 2>&1
netsh advfirewall firewall delete rule name="ReconcileHub Port 8000" >nul 2>&1
netsh advfirewall firewall delete rule name="ReconcileHub Python" >nul 2>&1

echo [2/4] Открытие входящих портов 8501 (Streamlit), 3000 (React) и 8000 (FastAPI)...
netsh advfirewall firewall add rule name="ReconcileHub Port 8501" dir=in action=allow protocol=TCP localport=8501 profile=any enable=yes >nul 2>&1
netsh advfirewall firewall add rule name="ReconcileHub Port 8501 UDP" dir=in action=allow protocol=UDP localport=8501 profile=any enable=yes >nul 2>&1
netsh advfirewall firewall add rule name="ReconcileHub Port 3000" dir=in action=allow protocol=TCP localport=3000 profile=any enable=yes >nul 2>&1
netsh advfirewall firewall add rule name="ReconcileHub Port 3000 UDP" dir=in action=allow protocol=UDP localport=3000 profile=any enable=yes >nul 2>&1
netsh advfirewall firewall add rule name="ReconcileHub Port 8000" dir=in action=allow protocol=TCP localport=8000 profile=any enable=yes >nul 2>&1
netsh advfirewall firewall add rule name="ReconcileHub Port 8000 UDP" dir=in action=allow protocol=UDP localport=8000 profile=any enable=yes >nul 2>&1

if %errorlevel% == 0 (
    echo   [✓] Порты 8501, 3000 и 8000 успешно открыты!
) else (
    echo   [!] Предупреждение: не удалось добавить правило порта.
)

echo.
echo [3/4] Добавление прямого разрешения для Python...
if defined REAL_PY (
    echo   Найден Python: "%REAL_PY%"
    netsh advfirewall firewall add rule name="ReconcileHub Python" dir=in action=allow program="%REAL_PY%" enable=yes profile=any >nul 2>&1
    echo   [✓] Python разрешен для сетевых входящих подключений!
) else (
    echo   [!] Путь к python.exe не определен автоматически, но порт 8501 открыт.
)

echo.
echo [4/4] Переключение текущего подключения в режим "Частная сеть" (Private)...
echo   (На "Общедоступных" сетях Windows блокирует обмен между компьютерами)
powershell -Command "Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue" >nul 2>&1
echo   [✓] Профиль сети обновлен на "Частная сеть".

echo.
echo =================================================================
echo  ГОТОВО! Доступ успешно настроен.
echo  Теперь коллеги в офисной сети смогут открыть ссылку в браузере.
echo =================================================================
echo.
pause

