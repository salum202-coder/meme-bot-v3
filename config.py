from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    default_chat_id: str = os.getenv("DEFAULT_CHAT_ID", "")
    port: int = int(os.getenv("PORT", "8080"))
    database_path: str = os.getenv("DATABASE_PATH", "data/meme_bot.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
    position_check_interval_seconds: int = int(os.getenv("POSITION_CHECK_INTERVAL_SECONDS", "30"))

    min_liquidity: float = float(os.getenv("MIN_LIQUIDITY", "20000"))
    min_volume_1h: float = float(os.getenv("MIN_VOLUME_1H", "50000"))
    min_txns_1h: int = int(os.getenv("MIN_TXNS_1H", "100"))
    max_token_age_hours: int = int(os.getenv("MAX_TOKEN_AGE_HOURS", "72"))

    watch_score_threshold: int = int(os.getenv("WATCH_SCORE_THRESHOLD", "65"))
    alert_score_threshold: int = int(os.getenv("ALERT_SCORE_THRESHOLD", "75"))
    entry_score_threshold: int = int(os.getenv("ENTRY_SCORE_THRESHOLD", "85"))

    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
    starting_balance: float = float(os.getenv("STARTING_BALANCE", "10"))
    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.10"))
    stop_loss_percent: float = float(os.getenv("STOP_LOSS_PERCENT", "10"))
    take_profit_percent: float = float(os.getenv("TAKE_PROFIT_PERCENT", "20"))
    trailing_stop_percent: float = float(os.getenv("TRAILING_STOP_PERCENT", "8"))
    enable_auto_paper_entry: bool = _get_bool("ENABLE_AUTO_PAPER_ENTRY", False)


settings = Settings()
