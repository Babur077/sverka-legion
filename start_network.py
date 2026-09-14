import subprocess
import socket
import sys
import webbrowser
import time

def get_all_local_ips():
    """Получает все активные локальные IPv4 адреса компьютера."""
    ips = set()
    # 1. Быстрый способ через сокет к внешнему DNS
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        if primary and not primary.startswith("127."):
            ips.add(primary)
    except Exception:
        pass

    # 2. Перебор всех сетевых адаптеров через getaddrinfo
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None):
            addr = item[4][0]
            if ":" not in addr and not addr.startswith("127."):
                ips.add(addr)
    except Exception:
        pass

    result = list(ips)
    return result if result else ["127.0.0.1"]

def main():
    ips = get_all_local_ips()
    port = 8501
    
    print("=" * 68)
    print("      🚀 Запуск ReconcileHub (Streamlit + Общая база SQLite)")
    print("=" * 68)
    print(" [✓] Общая база данных: database/reconcile_hub.db")
    print(f" [✓] Ссылка для вас на этом ПК: http://localhost:{port}")
    print("-" * 68)
    print(" [✓] Ссылки для коллег в офисной сети:")
    for ip in ips:
        print(f"     👉 http://{ip}:{port}")
    print("=" * 68)
    print(" 💡 ЕСЛИ У КОЛЛЕГ НЕ ОТКРЫВАЕТСЯ ССЫЛКА:")
    print(" 1. Запустите файл 'allow_firewall.bat' от имени администратора")
    print("    (Брандмауэр Windows часто по умолчанию блокирует входящие порты).")
    print(" 2. Убедитесь, что вы и коллеги подключены к одной сети Wi-Fi/LAN.")
    print(" 3. Проверьте, чтобы тип сети в Windows был 'Частная сеть' (Private).")
    print("=" * 68)
    print("\nЗапуск сервера (для остановки нажмите Ctrl + C)...")

    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address", "0.0.0.0",
        "--server.port", str(port),
        "--server.headless", "true"
    ]

    # Открываем браузер через пару секунд
    def open_browser():
        time.sleep(2)
        webbrowser.open(f"http://localhost:{port}")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nСервер остановлен.")

if __name__ == "__main__":
    main()
