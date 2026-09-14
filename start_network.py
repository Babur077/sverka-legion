import subprocess
import socket
import sys
import webbrowser
import time
import os
import re

def is_virtual_adapter(ip: str) -> bool:
    """Определяет, является ли IP адресом виртуального адаптера (VirtualBox, WSL, VMware, APIPA)."""
    if ip.startswith("127.") or ip.startswith("169.254."):
        return True
    if ip.startswith("192.168.56."):  # VirtualBox default Host-Only
        return True
    return False

def get_all_local_ips():
    """Получает и категоризирует все локальные IPv4 адреса."""
    primary_ip = None
    lan_ips = []
    other_ips = []

    # 1. Быстрый способ определить основной рабочий IP через исходящий маршрут
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        if primary and not primary.startswith("127.") and not is_virtual_adapter(primary):
            primary_ip = primary
    except Exception:
        pass

    # 2. Получение всех IPv4 адресов системы
    found = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = item[4][0]
            if addr and not addr.startswith("127."):
                found.add(addr)
    except Exception:
        pass

    # 3. На Windows также пробуем распарсить ipconfig для точности
    if sys.platform == "win32":
        try:
            out = subprocess.check_output("ipconfig", text=True, encoding="cp866", errors="ignore")
            for match in re.finditer(r"IPv4.*:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out):
                ip = match.group(1).strip()
                if not ip.startswith("127."):
                    found.add(ip)
        except Exception:
            pass

    for ip in found:
        if is_virtual_adapter(ip):
            other_ips.append(ip)
        else:
            if ip != primary_ip:
                lan_ips.append(ip)

    return primary_ip, lan_ips, other_ips

def check_and_free_port(port: int = 8501):
    """Проверяет, не занят ли порт 8501, и при необходимости завершает зависший streamlit процесс."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(('127.0.0.1', port)) != 0:
            return  # Порт свободен

    print(f" [!] Внимание: порт {port} уже кем-то занят.")
    if sys.platform == "win32":
        try:
            print("     Попытка освободить порт от предыдущего процесса...")
            out = subprocess.check_output(f'netstat -ano | findstr ":{port}"', shell=True, text=True, errors="ignore")
            for line in out.splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid and pid != "0" and pid != str(os.getpid()):
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            print("     [✓] Порт освобожден.")
        except Exception:
            pass

def main():
    port = 8501
    check_and_free_port(port)
    primary_ip, other_lan, virtual_ips = get_all_local_ips()
    
    recommended_ip = primary_ip or (other_lan[0] if other_lan else "127.0.0.1")

    print("=" * 70)
    print("      🚀 ReconcileHub — Запуск сервера сверок (Streamlit)")
    print("=" * 70)
    print(f" [✓] База данных: database/reconcile_hub.db (общая для всех коллег)")
    print(f" [✓] Для вас на этом компьютере:   http://localhost:{port}")
    print("-" * 70)
    print(" 📢 ССЫЛКА ДЛЯ ВАШИХ КОЛЛЕГ В ОФИСЕ (Wi-Fi / LAN):")
    print(f"     👉 http://{recommended_ip}:{port}   <--- (ОТПРАВЬТЕ ЭТУ ССЫЛКУ)")
    
    if other_lan:
        for ip in other_lan:
            print(f"     или http://{ip}:{port}")

    if virtual_ips:
        print("\n [!] Дополнительные виртуальные IP (не отправлять коллегам):")
        for ip in virtual_ips:
            print(f"     (виртуальный: {ip})")

    print("=" * 70)
    print(" 💡 ЧТО ДЕЛАТЬ, ЕСЛИ У КОЛЛЕГ ССЫЛКА НЕ ОТКРЫВАЕТСЯ:")
    print(" 1. Запустите 'allow_firewall.bat' (он сам откроет порт в Windows).")
    print(" 2. Убедитесь, что вы и коллеги подключены к одной сети Wi-Fi/роутеру.")
    print(" 3. Если роутер изолирует Wi-Fi клиентов (AP Isolation), запустите")
    print("    'start_tunnel.bat' — он создаст мгновенную онлайн-ссылку Cloudflare.")
    print("=" * 70)
    print("\nЗапуск приложения... (для остановки нажмите Ctrl + C)\n")

    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address", "0.0.0.0",
        "--server.port", str(port),
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--browser.gatherUsageStats", "false"
    ]

    # Открываем локальный браузер через 2 секунды
    def open_browser():
        time.sleep(2)
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nСервер ReconcileHub остановлен.")

if __name__ == "__main__":
    main()

