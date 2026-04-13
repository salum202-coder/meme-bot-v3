from __future__ import annotations

from utils.formatters import fmt_money, fmt_pct


def build_token_alert(token: dict, safety: dict, scores: dict, signal: dict) -> str:
    return (
        f"🎯 Meme Radar V3\n\n"
        f"Token: {token.get('symbol', 'UNKNOWN')}\n"
        f"Signal: {signal['signal']}\n"
        f"Reason: {signal['reason']}\n\n"
        f"Total Score: {scores['total_score']}/100\n"
        f"Safety: {scores['safety_score']}/40\n"
        f"Momentum: {scores['momentum_score']}/30\n"
        f"Structure: {scores['structure_score']}/20\n"
        f"Hype: {scores['hype_score']}/10\n\n"
        f"Price: {fmt_money(token.get('price'))}\n"
        f"Liquidity: {fmt_money(token.get('liquidity'))}\n"
        f"Volume 1h: {fmt_money(token.get('volume_1h'))}\n"
        f"Price Change 1h: {fmt_pct(token.get('price_change_1h'))}\n"
        f"Buys/Sells 1h: {token.get('buys_1h', 0)}/{token.get('sells_1h', 0)}\n"
        f"Risk: {safety['risk_level']}\n"
        f"Address: {token.get('address')}\n"
    )


def build_position_open_alert(position: dict) -> str:
    return (
        f"🧪 Paper Trade Opened\n\n"
        f"Token: {position.get('symbol', 'UNKNOWN')}\n"
        f"Entry: ${position['entry_price']:.8f}\n"
        f"Capital: ${position['allocated_capital']:.2f}\n"
        f"SL: ${position['stop_loss']:.8f}\n"
        f"TP: ${position['take_profit']:.8f}\n"
    )


def build_position_close_alert(position: dict, exit_price: float, pnl_amount: float, pnl_percent: float, reason: str) -> str:
    return (
        f"📉 Paper Trade Closed\n\n"
        f"Token: {position.get('symbol', 'UNKNOWN')}\n"
        f"Exit: ${exit_price:.8f}\n"
        f"PnL: ${pnl_amount:.2f} ({pnl_percent:.2f}%)\n"
        f"Reason: {reason}\n"
    )
