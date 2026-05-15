from __future__ import annotations

from utils.formatters import fmt_money, fmt_pct


def escape_md(text: str) -> str:
    if text is None:
        return ""
    chars = r"_*[]()~`>#+-=|{}.!"
    for ch in chars:
        text = text.replace(ch, f"\\{ch}")
    return text


def build_token_alert(token: dict, safety: dict, scores: dict, signal: dict) -> str:
    symbol = token.get("symbol", "UNKNOWN")
    address = token.get("address", "")
    risk = safety.get("risk_level", "unknown")
    reason = signal.get("reason", "")

    dex_url = token.get(
        "dex_url",
        f"https://dexscreener.com/solana/{address}"
    )

    return (
        f"🎯 Meme Radar V3\n\n"
        f"🪙 Token: {symbol}\n"
        f"🚨 Signal: {signal['signal']}\n"
        f"🧠 Reason: {reason}\n\n"
        f"📊 Total Score: {scores['total_score']}/100\n"
        f"🛡️ Safety: {scores['safety_score']}/40\n"
        f"🔥 Momentum: {scores['momentum_score']}/30\n"
        f"🏗️ Structure: {scores['structure_score']}/20\n"
        f"📣 Hype: {scores['hype_score']}/10\n\n"
        f"💰 Price: {fmt_money(token.get('price'))}\n"
        f"💧 Liquidity: {fmt_money(token.get('liquidity'))}\n"
        f"📈 Volume 1H: {fmt_money(token.get('volume_1h'))}\n"
        f"📉 Price Change 1H: {fmt_pct(token.get('price_change_1h'))}\n"
        f"🛒 Buys/Sells: {token.get('buys_1h', 0)}/{token.get('sells_1h', 0)}\n"
        f"⚠️ Risk: {risk}\n\n"
        f"📋 Contract Address:\n"
        f"{address}\n\n"
        f"🔗 DexScreener:\n{dex_url}"
    )


def build_position_open_alert(position: dict) -> str:
    symbol = position.get("symbol", "UNKNOWN")
    address = position.get("address", "")

    entry = float(position["entry_price"])
    capital = float(position["allocated_capital"])
    stop_loss = float(position["stop_loss"])
    take_profit = float(position["take_profit"])
    trailing = float(position["trailing_stop_percent"])

    sl_pct = ((stop_loss / entry) - 1) * 100
    tp_pct = ((take_profit / entry) - 1) * 100

    dex_url = f"https://dexscreener.com/solana/{address}"

    return (
        f"🟢 Paper Trade Opened\n\n"
        f"🪙 Token: {symbol}\n"
        f"💵 Capital: ${capital:.2f}\n\n"
        f"🎯 Entry: ${entry:.8f}\n"
        f"🛑 Stop Loss: ${stop_loss:.8f} ({sl_pct:.2f}%)\n"
        f"🏆 Take Profit: ${take_profit:.8f} (+{tp_pct:.2f}%)\n"
        f"📉 Trailing Stop: {trailing:.2f}%\n\n"
        f"📋 Contract:\n{address}\n\n"
        f"🔗 DexScreener:\n{dex_url}"
    )


def build_position_close_alert(
    position: dict,
    exit_price: float,
    pnl_amount: float,
    pnl_percent: float,
    reason: str,
) -> str:
    symbol = position.get("symbol", "UNKNOWN")
    address = position.get("address", "")
    entry_price = float(position["entry_price"])

    emoji = "✅" if pnl_amount >= 0 else "❌"
    result = "WIN" if pnl_amount > 0 else "LOSS" if pnl_amount < 0 else "BREAKEVEN"

    dex_url = f"https://dexscreener.com/solana/{address}"

    return (
        f"{emoji} Paper Trade Closed — {result}\n\n"
        f"🪙 Token: {symbol}\n"
        f"🎯 Entry: ${entry_price:.8f}\n"
        f"🚪 Exit: ${exit_price:.8f}\n\n"
        f"💰 PnL: ${pnl_amount:.2f} ({pnl_percent:.2f}%)\n"
        f"📝 Reason: {reason}\n\n"
        f"📋 Contract:\n{address}\n\n"
        f"🔗 DexScreener:\n{dex_url}"
    )
