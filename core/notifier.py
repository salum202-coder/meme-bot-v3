from __future__ import annotations

from utils.formatters import fmt_money, fmt_pct


def escape_md(text: str) -> str:
    """
    Escape Telegram MarkdownV2 special characters.
    """
    if text is None:
        return ""
    chars = r"_*[]()~`>#+-=|{}.!"
    for ch in chars:
        text = text.replace(ch, f"\\{ch}")
    return text


def build_token_alert(token: dict, safety: dict, scores: dict, signal: dict) -> str:
    symbol = escape_md(token.get("symbol", "UNKNOWN"))
    address = token.get("address", "")
    risk = escape_md(safety.get("risk_level", "unknown"))
    reason = escape_md(signal.get("reason", ""))

    dex_url = token.get(
        "dex_url",
        f"https://dexscreener.com/solana/{address}"
    )

    return (
        f"🎯 *Meme Radar V3*\n\n"
        f"🪙 *Token:* {symbol}\n"
        f"🚨 *Signal:* {signal['signal']}\n"
        f"🧠 *Reason:* {reason}\n\n"
        f"📊 *Total Score:* {scores['total_score']}/100\n"
        f"🛡️ *Safety:* {scores['safety_score']}/40\n"
        f"🔥 *Momentum:* {scores['momentum_score']}/30\n"
        f"🏗️ *Structure:* {scores['structure_score']}/20\n"
        f"📣 *Hype:* {scores['hype_score']}/10\n\n"
        f"💰 *Price:* {fmt_money(token.get('price'))}\n"
        f"💧 *Liquidity:* {fmt_money(token.get('liquidity'))}\n"
        f"📈 *Volume 1H:* {fmt_money(token.get('volume_1h'))}\n"
        f"📉 *Price Change 1H:* {fmt_pct(token.get('price_change_1h'))}\n"
        f"🛒 *Buys/Sells:* {token.get('buys_1h', 0)}/{token.get('sells_1h', 0)}\n"
        f"⚠️ *Risk:* {risk}\n\n"
        f"📋 *Contract Address:*\n"
        f"`{address}`\n\n"
        f"🔗 [Open on DexScreener]({dex_url})"
    )


def build_position_open_alert(position: dict) -> str:
    symbol = escape_md(position.get("symbol", "UNKNOWN"))

    return (
        f"🧪 *Paper Trade Opened*\n\n"
        f"🪙 *Token:* {symbol}\n"
        f"🎯 *Entry:* ${position['entry_price']:.8f}\n"
        f"💵 *Capital:* ${position['allocated_capital']:.2f}\n"
        f"🛑 *SL:* ${position['stop_loss']:.8f}\n"
        f"🏆 *TP:* ${position['take_profit']:.8f}\n"
    )


def build_position_close_alert(
    position: dict,
    exit_price: float,
    pnl_amount: float,
    pnl_percent: float,
    reason: str,
) -> str:
    symbol = escape_md(position.get("symbol", "UNKNOWN"))
    reason = escape_md(reason)

    emoji = "✅" if pnl_amount >= 0 else "❌"

    return (
        f"{emoji} *Paper Trade Closed*\n\n"
        f"🪙 *Token:* {symbol}\n"
        f"🚪 *Exit:* ${exit_price:.8f}\n"
        f"💰 *PnL:* ${pnl_amount:.2f} ({pnl_percent:.2f}%)\n"
        f"📝 *Reason:* {reason}\n"
    )
