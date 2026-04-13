from __future__ import annotations

from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from config import settings
from telegram_bot.handlers_start import start_handler
from telegram_bot.handlers_status import status_handler
from telegram_bot.handlers_wallet import wallet_handler
from telegram_bot.handlers_positions import positions_handler
from telegram_bot.callbacks import generic_callback_handler
from core.scheduler import run_scan_cycle, run_position_cycle


def build_bot_application():
    app = ApplicationBuilder().token(settings.telegram_token).build()
    app.bot_data["default_chat_id"] = settings.default_chat_id

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("wallet", wallet_handler))
    app.add_handler(CommandHandler("positions", positions_handler))
    app.add_handler(CallbackQueryHandler(generic_callback_handler))

    if app.job_queue is None:
        raise RuntimeError("Job queue is not available. Install PTB with job-queue extras if needed.")

    app.job_queue.run_repeating(run_scan_cycle, interval=settings.scan_interval_seconds, first=5)
    app.job_queue.run_repeating(run_position_cycle, interval=settings.position_check_interval_seconds, first=15)
    return app
