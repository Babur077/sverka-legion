import subprocess
import socket
import sys
import webbrowser
import time
import os
import re

PORT = 8501

def is_virtual_adapter(ip: str) -> bool:
    """Определяет, является ли IP адресом виртуального адаптера (VirtualBox, WSL, VMware, APIPA)."""
    if ip.startswith("127.") or ip.startswith("169.254."):
        return True
    if ip.startswith("192.168.56.") or ip.startswith("192.168.99."):  # VirtualBox default Host-Only
        return True
    return False

def _ip_plausibility_rank(ip: str) -> int:
    """Эвристическая оценка «похожести» IP на реальный адрес обычной
    домашней/офисной Wi-Fi/LAN-сети (чем меньше значение — тем правдоподобнее).

    Нужна для правильного выбора "запасных" IP из lan_ips, когда Способ 1
    (тест реальных маршрутов) не смог определить основной адрес — см.
    комментарий ниже, в get_all_local_ips().
    """
    try:
        first = int(ip.split(".")[0])
        second = int(ip.split(".")[1])
    except (ValueError, IndexError):
        return 9
    if ip.startswith("192.168."):
        return 0  # самый частый диапазон домашних/офисных Wi-Fi роутеров
    if first == 10:
        return 1  # частый диапазон офисных сетей (но также используется VPN)
    if first == 172 and 16 <= second <= 31:
        return 2  # чаще всего Docker Desktop / Hyper-V Default Switch / некоторые VPN
    return 3

def get_all_local_ips():
    """Надёжно определяет все локальные IPv4 адреса компьютера в офисной сети."""
    primary_ip = None
    lan_ips = []
    other_ips = []
    found_ips = set()

    # Способ 1: Тест маршрутов к типовым шлюзам (работает быстро, не требует реального интернета)
    test_gateways = [("8.8.8.8", 80), ("1.1.1.1", 80), ("192.168.1.1", 80), ("192.168.0.1", 80), ("10.0.0.1", 80)]
    for gw, gw_port in test_gateways:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            s.connect((gw, gw_port))
            sock_ip = s.getsockname()[0]
            s.close()
            if sock_ip and not sock_ip.startswith("127.") and not is_virtual_adapter(sock_ip):
                primary_ip = sock_ip
                found_ips.add(sock_ip)
                break
        except Exception:
            pass

    # Способ 2: Парсинг ipconfig на Windows (с поддержкой разных кодировок)
    if sys.platform == "win32":
        for enc in ["cp866", "utf-8", "cp1251"]:
            try:
                out = subprocess.check_output("ipconfig", text=True, encoding=enc, errors="ignore")
                matches = re.findall(r"(?:IPv4|IP-адрес)[^:\r\n]*:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out, re.IGNORECASE)
                for ip in matches:
                    ip = ip.strip()
                    if not ip.startswith("127."):
                        found_ips.add(ip)
                if matches:
                    break
            except Exception:
                pass

        # Способ 3: PowerShell Get-NetIPAddress
        try:
            ps_cmd = 'powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch \'Loopback|vEthernet|VirtualBox|VMware\' -and $_.IPAddress -notmatch \'^127\.|^169\.254\' } | Select-Object -ExpandProperty IPAddress"'
            ps_out = subprocess.check_output(ps_cmd, shell=True, text=True, errors="ignore")
            for line in ps_out.splitlines():
                ip = line.strip()
                if ip and re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                    found_ips.add(ip)
        except Exception:
            pass

    # Способ 4: getaddrinfo по имени хоста
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = item[4][0]
            if addr and not addr.startswith("127."):
                found_ips.add(addr)
    except Exception:
        pass

    for ip in found_ips:
        if is_virtual_adapter(ip):
            other_ips.append(ip)
        else:
            if ip != primary_ip:
                lan_ips.append(ip)

    # ИСПРАВЛЕНО: раньше порядок перебора lan_ips напрямую зависел от порядка
    # итерации по found_ips, который является обычным set() — а порядок
    # итерации по множеству в Python НЕ гарантирован и зависит от
    # рандомизации хешей конкретного запуска процесса. Из-за этого, если
    # Способ 1 (тест реальных маршрутов) не находил адрес — например, на
    # компьютере нет доступа в интернет, но локальная сеть работает — то
    # "основным" адресом для ссылки мог случайно стать IP виртуального
    # адаптера (Docker Desktop, Hyper-V Default Switch, активный VPN и т.п.),
    # до которого коллеги физически не могут достучаться по Wi-Fi/LAN — хотя
    # настоящий адрес обычной сети тоже был найден и просто оказывался ниже
    # в списке "запасных". Теперь кандидаты явно сортируются по
    # правдоподобности того, что это адрес обычной домашней/офисной сети
    # (192.168.x.x -> 10.x.x.x -> остальное), поэтому в качестве основной
    # ссылки выбирается наиболее вероятный вариант.
    lan_ips.sort(key=_ip_plausibility_rank)

    if not primary_ip and lan_ips:
        primary_ip = lan_ips.pop(0)

    return primary_ip, lan_ips, other_ips

def check_dependencies():
    """Проверяет наличие всех критически важных библиотек и устанавливает их при необходимости."""
    required = ["streamlit", "pandas", "polars", "openpyxl", "plotly", "fastexcel"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print("\n" + "=" * 72)
        print(f" [!] Внимание: отсутствуют необходимые пакеты: {', '.join(missing)}")
        print("     Выполняется автоматическая установка через pip...")
        print("=" * 72 + "\n")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=True)
            print("\n [✓] Все пакеты успешно установлены!\n")
        except Exception as e:
            print(f"\n [❌ ОШИБКА] Не удалось автоматически установить пакеты: {e}")
            print(f" Выполните команду вручную: pip install {' '.join(missing)}")
            try:
                input("\nНажмите Enter, чтобы закрыть окно...")
            except Exception:
                pass
            sys.exit(1)

def is_port_listening(port: int = PORT) -> bool:
    """Проверяет, отвечает ли порт 8501."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0

def check_and_free_port(port: int = PORT):
    """Надёжно завершает любые зависшие старые процессы на порту 8501."""
    if not is_port_listening(port):
        return

    print(f" [!] Внимание: порт {port} уже занят предыдущим процессом.")
    print("     Принудительное завершение зависшего сервера...")

    if sys.platform == "win32":
        # Шаг 1: Точечное завершение процесса, держащего порт через PowerShell
        try:
            ps_kill = f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Where-Object {{ $_.OwningProcess -gt 4 }} | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"'
            subprocess.run(ps_kill, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        # Шаг 2: Через netstat и taskkill
        try:
            out = subprocess.check_output(f'netstat -ano | findstr ":{port}"', shell=True, text=True, errors="ignore")
            for line in out.splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid and pid.isdigit() and int(pid) > 4 and pid != str(os.getpid()):
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    else:
        try:
            subprocess.run(f"fuser -k {port}/tcp", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # Ждём до 3 секунд освобождения порта
    for _ in range(6):
        time.sleep(0.5)
        if not is_port_listening(port):
            print("     [✓] Порт успешно освобождён!")
            return

    print("     [i] Порт остался активен — возможно, сервер уже запущен.")

def main():
    check_dependencies()
    port = PORT
    check_and_free_port(port)

    primary_ip, other_lan, virtual_ips = get_all_local_ips()
    recommended_ip = primary_ip or (other_lan[0] if other_lan else "127.0.0.1")

    print("\n" + "=" * 72)
    print("      🚀 ReconcileHub — Запуск сервера сверок (Локальная сеть)")
    print("=" * 72)
    print(" [✓] Режим: Локальная офисная сеть (100% конфиденциально, без интернета)")
    print(f" [✓] База данных: database/reconcile_hub.db (общая для всех коллег)")
    print(f" [✓] Ваш локальный адрес:  http://localhost:{port}")
    print("-" * 72)
    print(" 📢 ССЫЛКА ДЛЯ ВАШИХ КОЛЛЕГ В ОФИСЕ (Wi-Fi / LAN):")
    if recommended_ip != "127.0.0.1":
        print(f"     👉 http://{recommended_ip}:{port}   <--- (ОТПРАВЬТЕ ЭТУ ССЫЛКУ КОЛЛЕГАМ)")
    else:
        print("     [!] Сетевой адаптер не найден. Подключитесь к Wi-Fi или роутеру.")
        print(f"     👉 http://localhost:{port}")

    if other_lan:
        print("     Если ссылка выше не открывается у коллеги — попробуйте по очереди:")
        for ip in other_lan:
            print(f"     или http://{ip}:{port}")

    print("=" * 72)
    print(" 💡 ЕСЛИ У КОЛЛЕГ НЕ ОТКРЫВАЕТСЯ:")
    print(" 1. Запустите 'allow_firewall.bat' (он разрешит порт 8501 в Windows).")
    print(" 2. Убедитесь, что вы и коллеги подключены к одной Wi-Fi сети.")
    print(" 3. Проверьте, не включена изоляция клиентов (AP/Client Isolation) на роутере.")
    print(" 4. Если на этом ПК включен VPN — отключите его и запустите сервер заново.")
    print("=" * 72)
    print("\nЗапуск ReconcileHub в браузере...\n")

    # Авто-открытие браузера
    def open_browser():
        time.sleep(2)
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address", "0.0.0.0",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    ]

    try:
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print("\n" + "=" * 72)
            print(f" [❌ ОШИБКА] Streamlit завершился с кодом {res.returncode}.")
            print("=" * 72)
            print(" Возможные причины:")
            print(" 1. Ошибка в коде приложения или конфликт версий библиотек.")
            print(" 2. Порт 8501 заблокирован другой программой или антивирусом.")
            print(" 3. Запустите напрямую команду: streamlit run app.py")
            print("=" * 72)
            try:
                input("\nНажмите Enter, чтобы закрыть окно...")
            except Exception:
                pass
            sys.exit(res.returncode)
    except KeyboardInterrupt:
        print("\n[✓] Сервер ReconcileHub остановлен пользователем.")
        try:
            input("\nНажмите Enter для выхода...")
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        print(f"\n[❌ ОШИБКА] Не удалось запустить Streamlit: {e}")
        try:
            input("\nНажмите Enter, чтобы закрыть окно...")
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()