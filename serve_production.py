"""
Простой локальный сервер для раздачи готовой сборки (production dist).
Не требует установленного Node.js или node_modules на машине пользователя!
Запуск: python serve_production.py
"""
import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 3000
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

class SPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def do_GET(self):
        # Поддержка маршрутизации SPA: если файл не найден, отдавать index.html
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            index_path = os.path.join(DIST_DIR, "index.html")
            if os.path.exists(index_path) and not self.path.startswith("/assets/"):
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                with open(index_path, "rb") as f:
                    self.wfile.write(f.read())
                return
        return super().do_GET()

def main():
    if not os.path.exists(DIST_DIR):
        print("❌ Папка 'dist' не найдена.")
        print("💡 Сначала выполните сборку проекта: npm run build")
        sys.exit(1)

    url = f"http://localhost:{PORT}"
    print("=" * 60)
    print("🚀 Reconcile Hub (Production режим) успешно запущен!")
    print(f"🌐 Адрес в браузере: {url}")
    print("⚡ Для остановки сервера нажмите Ctrl+C")
    print("=" * 60)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    server = HTTPServer(("0.0.0.0", PORT), SPAHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен.")

if __name__ == "__main__":
    main()
