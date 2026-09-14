import os
import sys
import time
import socket
import subprocess
import threading
import re
import urllib.request
import shutil
import platform

PORT = 8501

def copy_to_clipboard(text: str):
    """Копирует текст в буфер обмена Windows / Linux / macOS."""
    try:
        if sys.platform == "win32":
            subprocess.run("clip", input=text.strip().encode("cp1251", errors="ignore"), shell=True)
            return True
        elif sys.platform == "darwin":
            subprocess.run("pbcopy", input=text.strip().encode("utf-8"), check=True)
            return True
        else:
            if shutil.which("xclip"):
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.strip().encode("utf-8"), check=True)
                return True
    except Exception:
        pass
    return False

def is_port_listening(host: str = "127.0.0.1", port: int = PORT) -> bool:
    """Проверяет, отвечает ли указанный порт."""
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def ensure_streamlit_running():
    """Проверяет, работает ли Streamlit, и запускает его при необходимости в фоне."""
    if is_port_listening("127.0.0.1", PORT):
        print(f" [✓] Локальный сервер ReconcileHub уже активен на порту {PORT}.")
        return None

    print(f" [i] Локальный сервер не активен. Запускаем ReconcileHub на порту {PORT}...")
    
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address", "0.0.0.0",
        "--server.port", str(PORT),
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--browser.gatherUsageStats", "false"
    ]

    # Запускаем в фоновом режиме
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    # Ждём готовности порта до 20 секунд
    print("     Ожидание готовности сервера...", end="", flush=True)
    for _ in range(25):
        time.sleep(1)
        print(".", end="", flush=True)
        if is_port_listening("127.0.0.1", PORT):
            print(" Готово!")
            print(f" [✓] Локальный сервер успешно запущен.")
            return proc

    print("\n [!] Предупреждение: Сервер долго отвечает, пробуем поднять туннель параллельно...")
    return proc

def download_cloudflared(target_path: str) -> bool:
    """Скачивает cloudflared.exe с GitHub с прогресс-баром и правильным User-Agent."""
    if sys.platform == "win32":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    elif sys.platform == "darwin":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64"
    else:
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

    print(" [i] Загрузка утилиты Cloudflare Tunnel (cloudflared)...")
    print(f"     Источник: {url}")
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        
        with urllib.request.urlopen(req, timeout=60) as response, open(target_path + ".tmp", "wb") as out_file:
            total_size = response.getheader("Content-Length")
            total_size = int(total_size) if total_size else None
            downloaded = 0
            block_size = 1024 * 1024  # 1 MB

            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                if total_size:
                    pct = int(downloaded / total_size * 100)
                    mb_cur = downloaded / (1024 * 1024)
                    mb_tot = total_size / (1024 * 1024)
                    print(f"\r     Загружено: {mb_cur:.1f} / {mb_tot:.1f} МБ ({pct}%)", end="", flush=True)
                else:
                    mb_cur = downloaded / (1024 * 1024)
                    print(f"\r     Загружено: {mb_cur:.1f} МБ", end="", flush=True)

        print("\n [✓] Загрузка завершена!")
        if os.path.exists(target_path):
            os.remove(target_path)
        os.rename(target_path + ".tmp", target_path)
        if sys.platform != "win32":
            os.chmod(target_path, 0o755)
        return True
    except Exception as e:
        print(f"\n [!] Ошибка скачивания Cloudflare: {e}")
        if os.path.exists(target_path + ".tmp"):
            try:
                os.remove(target_path + ".tmp")
            except Exception:
                pass
        return False

def show_banner(public_url: str, tunnel_type: str = "Cloudflare"):
    """Выводит крупный, хорошо заметный баннер с публичной ссылкой."""
    copied = copy_to_clipboard(public_url)
    
    print("\n" + "=" * 76)
    print(f"      🎉 ОНЛАЙН-ССЫЛКА RECONCILEHUB ДЛЯ ВАШИХ КОЛЛЕГ ({tunnel_type})")
    print("=" * 76)
    print()
    print("  👉  " + public_url)
    print()
    print("-" * 76)
    if copied:
        print("  [✓] ССЫЛКА АВТОМАТИЧЕСКИ СКОПИРОВАНА В БУФЕР ОБМЕНА (Ctrl + V)")
    print("  [✓] Отправьте эту ссылку коллегам в Telegram, WhatsApp, Teams или почту.")
    print("  [✓] Коллеги могут открывать её на любых компьютерах, смартфонах и планшетах.")
    print("  [✓] Не требуется настраивать Wi-Fi роутер или отключать брандмауэр.")
    print("-" * 76)
    print("  ⚠️  НЕ ЗАКРЫВАЙТЕ ЭТО ОКНО: пока оно открыто, коллеги могут работать.")
    print("     Для остановки нажмите Ctrl + C или просто закройте это окно.")
    print("=" * 76 + "\n")

    # Пробуем открыть в браузере
    try:
        import webbrowser
        time.sleep(1)
        webbrowser.open(public_url)
    except Exception:
        pass

def try_cloudflared() -> bool:
    """Запуск через Cloudflare Tunnel."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cf_exe = os.path.join(script_dir, "cloudflared.exe" if sys.platform == "win32" else "cloudflared")

    # Проверяем, есть ли в PATH или в папке
    if not os.path.exists(cf_exe):
        which_cf = shutil.which("cloudflared")
        if which_cf:
            cf_exe = which_cf
        else:
            ok = download_cloudflared(cf_exe)
            if not ok or not os.path.exists(cf_exe):
                return False

    print("\n [1/3] Запуск защищенного туннеля Cloudflare...")
    cmd = [cf_exe, "tunnel", "--url", f"http://127.0.0.1:{PORT}"]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
    except Exception as e:
        print(f" [!] Ошибка запуска cloudflared: {e}")
        return False

    found_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")

    # Читаем вывод cloudflared
    try:
        start_time = time.time()
        for line in proc.stdout:
            # Ищем ссылку
            match = url_pattern.search(line)
            if match and not found_url:
                found_url = match.group(0)
                show_banner(found_url, "Cloudflare Tunnel")
            
            # Если еще не нашли и прошло больше 30 секунд — возможно ошибка
            if not found_url and time.time() - start_time > 30:
                print("\n [!] Превышено время ожидания ссылки Cloudflare.")
                proc.terminate()
                return False
                
        proc.wait()
    except KeyboardInterrupt:
        print("\nОстановка туннеля...")
        proc.terminate()
        return True
    except Exception as e:
        print(f"\n [!] Ошибка при работе туннеля: {e}")
        proc.terminate()
        return False

    return bool(found_url)

def try_pinggy() -> bool:
    """Резервный вариант через Pinggy SSH (порт 443 — никогда не блокируется)."""
    if not shutil.which("ssh"):
        return False

    print("\n [2/3] Запуск резервного туннеля через Pinggy (порт 443)...")
    cmd = [
        "ssh", "-p", "443",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-R0:localhost:8501",
        "a.pinggy.io"
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
    except Exception as e:
        print(f" [!] Ошибка запуска SSH: {e}")
        return False

    found_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.a\.pinggy\.link")

    try:
        start_time = time.time()
        for line in proc.stdout:
            match = url_pattern.search(line)
            if match and not found_url:
                found_url = match.group(0)
                show_banner(found_url, "Pinggy Tunnel")

            if not found_url and time.time() - start_time > 20:
                proc.terminate()
                return False

        proc.wait()
    except KeyboardInterrupt:
        print("\nОстановка туннеля...")
        proc.terminate()
        return True
    except Exception:
        proc.terminate()
        return False

    return bool(found_url)

def try_localhost_run() -> bool:
    """Резервный вариант через localhost.run (SSH)."""
    if not shutil.which("ssh"):
        return False

    print("\n [3/3] Запуск резервного туннеля через Localhost.run...")
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-R", f"80:localhost:{PORT}",
        "nokey@localhost.run"
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
    except Exception as e:
        return False

    found_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.lhr\.life")

    try:
        start_time = time.time()
        for line in proc.stdout:
            match = url_pattern.search(line)
            if match and not found_url:
                found_url = match.group(0)
                show_banner(found_url, "Localhost.run")

            if not found_url and time.time() - start_time > 20:
                proc.terminate()
                return False

        proc.wait()
    except KeyboardInterrupt:
        print("\nОстановка туннеля...")
        proc.terminate()
        return True
    except Exception:
        proc.terminate()
        return False

    return bool(found_url)

def main():
    print("=" * 76)
    print("      🌐 ReconcileHub — Запуск с онлайн-ссылкой для всех коллег")
    print("=" * 76)
    print()
    print(" Этот режим создает безопасный интернет-адрес (HTTPS) для вашей программы.")
    print(" Ваши коллеги смогут подключиться с любого компьютера, телефона или филиала.")
    print("-" * 76)

    # 1. Запуск или проверка Streamlit
    ensure_streamlit_running()

    # 2. Попытка Cloudflare Tunnel
    if try_cloudflared():
        return

    # 3. Попытка Pinggy
    print("\n [!] Cloudflare не ответил, переключаемся на Pinggy...")
    if try_pinggy():
        return

    # 4. Попытка Localhost.run
    print("\n [!] Pinggy не ответил, переключаемся на Localhost.run...")
    if try_localhost_run():
        return

    # Если ничего не помогло
    print("\n" + "=" * 76)
    print(" [❌ ОШИБКА] Не удалось автоматически поднять интернет-туннель.")
    print("=" * 76)
    print(" Возможные причины:")
    print(" 1. Нет подключения к интернету на этом компьютере.")
    print(" 2. Антивирус или корпоративный брандмауэр блокирует скачивание утилит.")
    print()
    print(" РЕШЕНИЕ ВРУЧНУЮ:")
    print(" 1. Скачайте официальный файл 'cloudflared-windows-amd64.exe':")
    print("    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe")
    print(" 2. Переименуйте его в 'cloudflared.exe' и положите в эту же папку ReconcileHub.")
    print(" 3. Запустите 'start_tunnel.bat' снова.")
    print("=" * 76)
    print()
    try:
        input("Нажмите Enter для завершения...")
    except Exception:
        pass

if __name__ == "__main__":
    main()
