from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from config import settings


def init_db() -> None:
    os.makedirs(os.path.dirname(settings.database_path), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS discovered_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                symbol TEXT,
                name TEXT,
                source TEXT,
                discovered_at TEXT,
                last_signal TEXT,
                last_total_score REAL
            );

            CREATE TABLE IF NOT EXISTS token_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL,
                liquidity REAL,
                volume_1h REAL,
                buys_1h INTEGER,
                sells_1h INTEGER,
                market_cap REAL,
                total_score REAL,
                signal TEXT
            );

            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                symbol TEXT,
                entry_price REAL NOT NULL,
                quantity REAL NOT NULL,
                allocated_capital REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                trailing_stop_percent REAL NOT NULL,
                highest_price REAL NOT NULL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                symbol TEXT,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                quantity REAL NOT NULL,
                allocated_capital REAL NOT NULL,
                pnl_amount REAL NOT NULL,
                pnl_percent REAL NOT NULL,
                entry_reason TEXT,
                exit_reason TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
