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
    base_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(base_dir, "dist.zip")

    if not os.path.exists(DIST_DIR):
        if os.path.exists(zip_path):
            print("📦 Обнаружен архив 'dist.zip'. Распаковка готовой сборки...")
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(base_dir)
            print("✅ Сборка успешно распакована в папку 'dist'!")
        else:
            print("❌ Папка 'dist' не найдена.")
            print("")
            print("💡 У вас есть 2 простых варианта запуска:")
            print("   1) Если вам нужен классический Streamlit-интерфейс:")
            print("      Запустите команду: streamlit run app.py")
            print("      (Для неё папка 'dist' и node_modules вообще не нужны!)")
            print("")
            print("   2) Если вам нужен веб-интерфейс React:")
            print("      Положите файл 'dist.zip' (или папку 'dist') в корень проекта,")
            print("      скачав свежую версию из AI Studio (Settings -> Export ZIP).")
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
