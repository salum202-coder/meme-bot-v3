from __future__ import annotations

from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes

from core.wallet_watcher import (
    WATCH_WALLETS,
    build_copy_positions_message,
    build_copy_trades_message,
    build_copy_wallet_message,
    manual_close_paper_copy_trade,
    build_cluster_discovery_message,
    build_pattern_brain_message,
)
from storage.repository_wallet_watch import get_wallet_watch_states


def _short(value: str, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


async def _reply_long_text(update: Update, text: str, chunk_size: int = 3500) -> None:
    """
    Telegram has a message length limit.
    This helper splits long reports into safe chunks.
    Also prevents silent failure when the message is empty.
    """
    message = update.effective_message

    if not message:
        return

    if not text or not text.strip():
        await message.reply_text("No data available yet.")
        return

    lines = text.splitlines()
    current = ""

    for line in lines:
        next_text = current + line + "\n"

        if len(next_text) >= chunk_size:
            if current.strip():
                await message.reply_text(
                    current.strip(),
                    disable_web_page_preview=True,
                )
            current = line + "\n"
        else:
            current = next_text

    if current.strip():
        await message.reply_text(
            current.strip(),
            disable_web_page_preview=True,
        )


def _set_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id


async def cluster_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    states = get_wallet_watch_states()
    state_by_wallet = {item["wallet_address"]: item for item in states}

    lines = [
        "🕵️ Wallet Cluster Watch",
        "",
        f"Watched wallets: {len(WATCH_WALLETS)}",
        "Mode: Alerts only",
        "Auto entry: OFF",
        "",
    ]

    for label, wallet in WATCH_WALLETS.items():
        state = state_by_wallet.get(wallet)
        last_seen = state.get("last_seen_at") if state else "Not initialized yet"
        last_sig = state.get("last_signature") if state else None

        lines.extend(
            [
                f"• {label}",
                f"Wallet: {_short(wallet)}",
                f"Last seen: {last_seen or 'N/A'}",
                f"Last tx: {_short(last_sig) if last_sig else 'N/A'}",
                "",
            ]
        )

    await _reply_long_text(update, "\n".join(lines))


async def copy_positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        await _reply_long_text(update, build_copy_positions_message())
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Copy Positions error:\n{type(e).__name__}: {e}"
        )


async def copy_trades_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        await _reply_long_text(update, build_copy_trades_message(limit=10))
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Copy Trades error:\n{type(e).__name__}: {e}"
        )


async def copy_wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        await _reply_long_text(update, build_copy_wallet_message())
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Copy Wallet error:\n{type(e).__name__}: {e}"
        )


def _first_arg(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    args = getattr(context, "args", None) or []
    return args[0] if args else None


async def copy_close_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        await _reply_long_text(
            update,
            manual_close_paper_copy_trade(Decimal("100"), mint_arg=_first_arg(context)),
        )
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Close Copy All error:\n{type(e).__name__}: {e}"
        )


async def copy_close_50_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        await _reply_long_text(
            update,
            manual_close_paper_copy_trade(Decimal("50"), mint_arg=_first_arg(context)),
        )
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Close Copy 50% error:\n{type(e).__name__}: {e}"
        )


async def copy_close_25_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        await _reply_long_text(
            update,
            manual_close_paper_copy_trade(Decimal("25"), mint_arg=_first_arg(context)),
        )
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Close Copy 25% error:\n{type(e).__name__}: {e}"
        )


async def cluster_map_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        message = build_cluster_discovery_message()
        await _reply_long_text(update, message)
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Cluster Map error:\n{type(e).__name__}: {e}"
        )


async def pattern_brain_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_chat_id(update, context)

    try:
        message = build_pattern_brain_message()
        await _reply_long_text(update, message)
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Pattern Brain error:\n{type(e).__name__}: {e}"
        )
