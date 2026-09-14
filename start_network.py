import subprocess
import socket
import sys
import webbrowser
import time

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    local_ip = get_local_ip()
    port = 8501
    
    print("=" * 65)
    print("      🚀 Запуск ReconcileHub (Streamlit + Общая база SQLite)")
    print("=" * 65)
    print(" [✓] База данных:       database/reconcile_hub.db (единая для всех)")
    print(f" [✓] Ссылка для вас:    http://localhost:{port}")
    print(f" [✓] Ссылка для коллег: http://{local_ip}:{port}")
    print("=" * 65)
    print(" Коллеги в офисе/сети могут открыть ссылку со своих компьютеров")
    print(" и сразу видеть все банки, терминалы и архив сверок!")
    print(" Для остановки сервера нажмите Ctrl + C в этом окне.")
    print("=" * 65)
    print("\nЗапуск сервера...")

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
