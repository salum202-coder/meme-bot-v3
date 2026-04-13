from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from storage.db import init_db
from telegram_bot.bot import build_bot_application
from utils.logger import setup_logger
from config import settings

logger = setup_logger("app")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Meme Bot V3 Starter is live")


def start_health_server() -> None:
    server = HTTPServer(("0.0.0.0", settings.port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Health server started on port %s", settings.port)


def main() -> None:
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_TOKEN is missing. Put a NEW token in .env")
    init_db()
    start_health_server()
    app = build_bot_application()
    logger.info("Starting Meme Bot V3 Starter")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
