from __future__ import annotations

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import settings
from telegram_bot.handlers_start import start_handler
from telegram_bot.handlers_status import status_handler
from telegram_bot.handlers_wallet import wallet_handler
from telegram_bot.handlers_positions import positions_handler
from telegram_bot.handlers_trades import trades_handler
from telegram_bot.handlers_wallet_watch import (
    wallet_links_handler,
    cluster_handler,
    copy_positions_handler,
    copy_trades_handler,
    copy_wallet_handler,
    copy_close_all_handler,
    copy_close_50_handler,
    copy_close_25_handler,
    cluster_map_handler,
    pattern_brain_handler,
    exit_ranking_handler,
    entry_debug_handler,
    forensics_handler,
)
from telegram_bot.handlers_digest import digest_handler
from telegram_bot.handlers_menu import menu_handler
from telegram_bot.callbacks import generic_callback_handler
from core.scheduler import run_scan_cycle, run_position_cycle
from core.wallet_watcher import run_wallet_watch_cycle
from core.wallet_digest import run_wallet_digest_cycle


def build_bot_application():
    app = ApplicationBuilder().token(settings.telegram_token).build()
    app.bot_data["default_chat_id"] = settings.default_chat_id

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("wallet", wallet_handler))
    app.add_handler(CommandHandler("positions", positions_handler))
    app.add_handler(CommandHandler("trades", trades_handler))
    app.add_handler(CommandHandler("cluster", cluster_handler))
    app.add_handler(CommandHandler("watch_wallets", cluster_handler))
    app.add_handler(CommandHandler("cluster_map", cluster_map_handler))
    app.add_handler(CommandHandler("pattern_brain", pattern_brain_handler))
    app.add_handler(CommandHandler("exit_ranking", exit_ranking_handler))
    app.add_handler(CommandHandler("entry_debug", entry_debug_handler))
    app.add_handler(CommandHandler("forensics", forensics_handler))
    app.add_handler(CommandHandler("links", wallet_links_handler))
    app.add_handler(CommandHandler("copy_positions", copy_positions_handler))
    app.add_handler(CommandHandler("copy_trades", copy_trades_handler))
    app.add_handler(CommandHandler("copy_wallet", copy_wallet_handler))
    app.add_handler(CommandHandler("copy_close_all", copy_close_all_handler))
    app.add_handler(CommandHandler("copy_close_50", copy_close_50_handler))
    app.add_handler(CommandHandler("copy_close_25", copy_close_25_handler))
    app.add_handler(CommandHandler("digest", digest_handler))
    app.add_handler(CallbackQueryHandler(generic_callback_handler))

    # Fixed Telegram control panel buttons.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    if app.job_queue is None:
        raise RuntimeError("Job queue is not available. Install PTB with job-queue extras if needed.")

    app.job_queue.run_repeating(run_scan_cycle, interval=settings.scan_interval_seconds, first=5)
    app.job_queue.run_repeating(run_position_cycle, interval=settings.position_check_interval_seconds, first=15)

    # Wallet Watch - important alerts.
    app.job_queue.run_repeating(run_wallet_watch_cycle, interval=20, first=10)

    # V4.23: Wallet Cluster Digest auto-job disabled to remove 30m Telegram spam.
    # Manual /digest command remains available if you need it.

    return app
