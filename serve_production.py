"""
Быстрый локальный сервер для раздачи готовой сборки (production dist).
Не требует установленного Node.js или node_modules на машине пользователя!
Запуск: python serve_production.py
"""
import os
import sys
import mimetypes
import webbrowser
from http.server import SimpleHTTPRequestHandler

try:
    from http.server import ThreadingHTTPServer as BaseServer
except ImportError:
    from socketserver import ThreadingMixIn
    from http.server import HTTPServer
    class BaseServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

DEFAULT_PORT = 3000
FALLBACK_PORTS = [3000, 3001, 8080, 8000, 5000]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")

# Инициализируем корректные MIME-типы (включая js и css)
mimetypes.init()
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class FastSPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def address_string(self):
        # Предотвращает медленный обратный DNS lookup на Windows (gethostbyaddr),
        # из-за которого сервер может зависать на 5-15 секунд при каждом запросе
        return self.client_address[0]

    def log_message(self, format, *args):
        # Компактный вывод в консоль для подтверждения работы
        sys.stdout.write(f"  [{self.log_date_time_string()}] {self.address_string()} - {format % args}\n")
        sys.stdout.flush()

    def do_GET(self):
        # 1. Если запрашивается корень или путь SPA
        translated = self.translate_path(self.path)

        # Если файл существует и это обычный файл (например /assets/index-xxx.js или favicon)
        if os.path.isfile(translated):
            return super().do_GET()

        # Если это директория и в ней есть index.html (например корень /)
        if os.path.isdir(translated):
            index_candidate = os.path.join(translated, "index.html")
            if os.path.isfile(index_candidate):
                self._send_file(index_candidate, "text/html; charset=utf-8")
                return

        # SPA-маршрутизация: если запрашиваемый путь не файл и не в assets, отдаем dist/index.html
        if not self.path.startswith("/assets/"):
            index_path = os.path.join(DIST_DIR, "index.html")
            if os.path.isfile(index_path):
                self._send_file(index_path, "text/html; charset=utf-8")
                return

        # Если ресурс в /assets/ действительно не найден
        self.send_error(404, "File not found")

    def _send_file(self, filepath, content_type=None):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
        except OSError:
            self.send_error(404, "File not found")
            return

        if not content_type:
            content_type, _ = mimetypes.guess_type(filepath)
            if not content_type:
                content_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if filepath.endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        elif "/assets/" in filepath.replace("\\", "/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(content)


def unpack_if_needed():
    zip_path = os.path.join(BASE_DIR, "dist.zip")
    index_file = os.path.join(DIST_DIR, "index.html")

    if not os.path.exists(DIST_DIR) or not os.path.exists(index_file):
        if os.path.exists(zip_path):
            print("📦 Обнаружен архив 'dist.zip'. Распаковка готовой сборки...")
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(BASE_DIR)
            print("✅ Сборка успешно распакована в папку 'dist'!")
        else:
            print("❌ Папка 'dist' или файл 'dist/index.html' не найдены.")
            print("")
            print("💡 У вас есть 2 простых варианта:")
            print("   1) Для запуска Streamlit (классический интерфейс):")
            print("      streamlit run app.py")
            print("")
            print("   2) Для запуска React (современный интерфейс):")
            print("      Убедитесь, что папка 'dist' находится в проекте.")
            sys.exit(1)


def create_server():
    unpack_if_needed()

    for port in FALLBACK_PORTS:
        try:
            BaseServer.allow_reuse_address = True
            server = BaseServer(("0.0.0.0", port), FastSPAHandler)
            return server, port
        except OSError:
            continue

    # Если стандартные порты заняты, берем случайный свободный порт
    server = BaseServer(("0.0.0.0", 0), FastSPAHandler)
    return server, server.server_port


def main():
    server, port = create_server()
    url = f"http://127.0.0.1:{port}"

    print("=" * 60)
    print("🚀 Reconcile Hub (Production режим) успешно запущен!")
    print(f"🌐 Адрес в браузере: {url}")
    print(f"📁 Раздача статики из: {DIST_DIR}")
    print("⚡ Для остановки сервера нажмите Ctrl+C")
    print("=" * 60)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен пользователем.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

