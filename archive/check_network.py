import sys
import socket
import subprocess
import os

def print_header(title):
    print("\n" + "=" * 65)
    print(f"  🔍 {title}")
    print("=" * 65)

def check_python_environment():
    print_header("1. Проверка окружения Python")
    print(f"Версия Python: {sys.version.split()[0]} ({sys.executable})")
    
    required_packages = ["streamlit", "pandas", "polars", "openpyxl", "plotly"]
    all_ok = True
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f"  [✓] {pkg} — установлен")
        except ImportError:
            print(f"  [✗] {pkg} — НЕ УСТАНОВЛЕН! (Запустите: pip install -r requirements.txt)")
            all_ok = False
    return all_ok

def check_local_server():
    print_header("2. Проверка локального сервера (порт 8501)")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        res = s.connect_ex(('127.0.0.1', 8501))
        if res == 0:
            print("  [✓] Сервер ReconcileHub сейчас ЗАПУЩЕН и принимает подключения!")
            return True
        else:
            print("  [!] Сервер сейчас НЕ запущен на порту 8501.")
            print("      Запустите start_streamlit.bat или start.bat.")
            return False

def check_ips():
    print_header("3. Сетевые адреса (IP) вашего компьютера")
    try:
        from start_network import get_all_local_ips
        primary, lan_ips, _ = get_all_local_ips()
    except Exception:
        primary = None
        lan_ips = []

    if primary and primary != "127.0.0.1":
        print(f"  👉 Главный IP адрес для коллег: http://{primary}:8501")
        print("     (Именно эту ссылку отправьте коллегам в чат)")
        if lan_ips:
            for ip in lan_ips:
                print(f"     или запасной IP: http://{ip}:8501")
    else:
        print("  [!] Не удалось определить основной сетевой IP.")

    hostname = socket.gethostname()
    print(f"  Имя компьютера в сети: {hostname}")
    print(f"  Альтернативная ссылка по имени: http://{hostname}:8501")

def check_firewall():
    print_header("4. Проверка Брандмауэра Windows и профиля сети")
    if sys.platform != "win32":
        print("  (Проверка фаервола актуальна для Windows)")
        return

    # Проверка правил фаервола
    try:
        out = subprocess.check_output('netsh advfirewall firewall show rule name="ReconcileHub Port 8501"', shell=True, text=True, errors="ignore")
        if "ReconcileHub Port 8501" in out:
            print("  [✓] Правило для порта 8501 в Брандмауэре Windows найдено и активно.")
        else:
            print("  [!] Внимание: правило для порта 8501 не найдено.")
            print("      Запустите allow_firewall.bat от имени администратора!")
    except Exception:
        print("  [!] Правило для порта 8501 не настроено в Брандмауэре.")
        print("      Запустите allow_firewall.bat от имени администратора!")

    # Проверка типа сети (Private vs Public)
    try:
        ps_cmd = 'powershell -Command "Get-NetConnectionProfile | Select-Object -ExpandProperty NetworkCategory"'
        cat = subprocess.check_output(ps_cmd, shell=True, text=True, errors="ignore").strip()
        if "Public" in cat:
            print(f"  [ВНИМАНИЕ] Текущая сеть определена как '{cat}' (Общедоступная)!")
            print("  Windows блокирует входящие подключения на общедоступных сетях.")
            print("  Решение: запустите allow_firewall.bat — он автоматически переключит в 'Private'.")
        elif "Private" in cat:
            print(f"  [✓] Профиль сети: Частная сеть (Private) — входящие подключения разрешены.")
        else:
            print(f"  Профиль сети: {cat}")
    except Exception:
        pass

def main():
    print("\n" + "#" * 65)
    print("   ЭКСПРЕСС-ДИАГНОСТИКА СЕТЕВОГО ПОДКЛЮЧЕНИЯ RECONCILEHUB")
    print("#" * 65)

    check_python_environment()
    check_local_server()
    check_ips()
    check_firewall()

    print_header("Итог и рекомендации")
    print("Если у коллег всё равно пишет 'Не удается получить доступ к сайту':")
    print(" 1. Запустите 'allow_firewall.bat' (он откроет порт и снимет блокировку).")
    print(" 2. Если в офисе включена изоляция клиентов Wi-Fi (роутер не пускает):")
    print("    -> Запустите 'start_tunnel.bat' — он создаст онлайн-ссылку Cloudflare,")
    print("       которая работает гарантированно через интернет без настроек сети.")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
