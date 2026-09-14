@echo off
chcp 65001 > nul
title Настройка Брандмауэра Windows для ReconcileHub

echo =================================================================
echo       Разрешение сетевого доступа к ReconcileHub в Брандмауэре
echo =================================================================
echo.
echo Этот скрипт откроет входящий порт 8501 в Брандмауэре Windows,
echo чтобы коллеги могли подключаться к серверу по локальной сети.
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ВНИМАНИЕ] Требуются права Администратора!
    echo Пожалуйста, нажмите правой кнопкой мыши по этому файлу
    echo и выберите: "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

echo [1/2] Добавление правила для порта 8501 (TCP)...
netsh advfirewall firewall delete rule name="ReconcileHub Port 8501" >nul 2>&1
netsh advfirewall firewall add rule name="ReconcileHub Port 8501" dir=in action=allow protocol=TCP localport=8501 >nul 2>&1

if %errorlevel% == 0 (
    echo [УСПЕХ] Порт 8501 успешно открыт в Брандмауэре Windows!
) else (
    echo [ОШИБКА] Не удалось добавить правило порта.
)

echo.
echo [2/2] Добавление правила для Python...
netsh advfirewall firewall add rule name="Python Inbound ReconcileHub" dir=in action=allow program="%~dp0python.exe" enable=yes >nul 2>&1

echo.
echo =================================================================
echo  ГОТОВО! Теперь компьютеры коллег смогут подключиться к вашему ПК.
echo  Запустите start_streamlit.bat и отправьте ссылку коллегам.
echo =================================================================
echo.
pause
