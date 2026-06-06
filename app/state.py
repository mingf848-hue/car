from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import CopyResult, WalletTrade


class StateStore:
    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.sqlite_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_trades (
                    trade_id TEXT PRIMARY KEY,
                    wallet TEXT NOT NULL,
                    seen_at INTEGER NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS wallet_state (
                    wallet TEXT PRIMARY KEY,
                    initialized_at INTEGER NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS copy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    trade_id TEXT,
                    wallet TEXT,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    market_slug TEXT,
                    token_id TEXT,
                    outcome TEXT,
                    amount_usdc REAL NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS token_cooldowns (
                    token_id TEXT PRIMARY KEY,
                    last_action_at INTEGER NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    token_id TEXT PRIMARY KEY,
                    market_slug TEXT,
                    outcome TEXT,
                    open_shares REAL NOT NULL DEFAULT 0,
                    avg_entry_price REAL NOT NULL DEFAULT 0,
                    total_buy_usdc REAL NOT NULL DEFAULT 0,
                    total_sell_usdc REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'open',
                    updated_at INTEGER NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS position_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    trade_id TEXT,
                    token_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    shares REAL NOT NULL,
                    price REAL NOT NULL DEFAULT 0,
                    usdc_value REAL NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS followed_wallets (
                    wallet TEXT PRIMARY KEY,
                    label TEXT,
                    source TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def is_wallet_initialized(self, wallet: str) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT wallet FROM wallet_state WHERE wallet = ?",
                (wallet.lower(),),
            ).fetchone()
            return row is not None

    def initialize_wallet(self, wallet: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO wallet_state(wallet, initialized_at) VALUES (?, ?)",
                (wallet.lower(), int(time.time())),
            )

    def upsert_followed_wallet(self, wallet: str, label: str = "", source: str = "manual", active: bool = True) -> None:
        normalized = wallet.lower().strip()
        now = int(time.time())
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO followed_wallets(wallet, label, source, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(wallet) DO UPDATE SET
                    label = COALESCE(NULLIF(excluded.label, ''), followed_wallets.label),
                    source = excluded.source,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (normalized, label.strip(), source.strip(), 1 if active else 0, now, now),
            )

    def set_followed_wallet_active(self, wallet: str, active: bool) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE followed_wallets SET active = ?, updated_at = ? WHERE wallet = ?",
                (1 if active else 0, int(time.time()), wallet.lower().strip()),
            )

    def followed_wallets(self, include_inactive: bool = True) -> List[Dict[str, Any]]:
        query = "SELECT * FROM followed_wallets"
        if not include_inactive:
            query += " WHERE active = 1"
        query += " ORDER BY active DESC, updated_at DESC"
        with self._connect() as con:
            rows = con.execute(query).fetchall()
        return [dict(row) for row in rows]

    def active_followed_wallet_addresses(self) -> List[str]:
        return [item["wallet"] for item in self.followed_wallets(include_inactive=False)]

    def has_seen(self, trade_id: str) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT trade_id FROM seen_trades WHERE trade_id = ?",
                (trade_id,),
            ).fetchone()
            return row is not None

    def mark_seen(self, trade: WalletTrade) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO seen_trades(trade_id, wallet, seen_at) VALUES (?, ?, ?)",
                (trade.trade_id, trade.wallet.lower(), int(time.time())),
            )

    def token_on_cooldown(self, token_id: str, cooldown_seconds: int) -> bool:
        if not token_id or cooldown_seconds <= 0:
            return False
        with self._connect() as con:
            row = con.execute(
                "SELECT last_action_at FROM token_cooldowns WHERE token_id = ?",
                (token_id,),
            ).fetchone()
        if row is None:
            return False
        return int(time.time()) - int(row["last_action_at"]) < cooldown_seconds

    def touch_token_cooldown(self, token_id: str) -> None:
        if not token_id:
            return
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO token_cooldowns(token_id, last_action_at)
                VALUES (?, ?)
                ON CONFLICT(token_id) DO UPDATE SET last_action_at = excluded.last_action_at
                """,
                (token_id, int(time.time())),
            )

    def live_spend_today(self) -> float:
        now = int(time.time())
        start = now - (now % 86400)
        with self._connect() as con:
            row = con.execute(
                """
                SELECT COALESCE(SUM(amount_usdc), 0) AS spend
                FROM copy_events
                WHERE created_at >= ? AND action = 'live_buy'
                """,
                (start,),
            ).fetchone()
        return float(row["spend"] if row else 0)

    def record_result(self, result: CopyResult) -> None:
        trade = result.trade
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO copy_events(
                    created_at, trade_id, wallet, action, reason, market_slug,
                    token_id, outcome, amount_usdc, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    trade.trade_id if trade else None,
                    trade.wallet.lower() if trade else None,
                    result.action,
                    result.reason,
                    trade.market_slug if trade else None,
                    trade.token_id if trade else None,
                    trade.outcome if trade else None,
                    float(result.amount_usdc),
                    json.dumps(result.payload, ensure_ascii=True, default=str),
                ),
            )

    def record_position_buy(
        self,
        trade: WalletTrade,
        amount_usdc: float,
        shares: float,
        price: float,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = int(time.time())
        with self._connect() as con:
            row = con.execute(
                "SELECT open_shares, total_buy_usdc FROM positions WHERE token_id = ?",
                (trade.token_id,),
            ).fetchone()
            if row:
                new_shares = float(row["open_shares"]) + float(shares)
                new_buy = float(row["total_buy_usdc"]) + float(amount_usdc)
                avg_price = new_buy / new_shares if new_shares else 0
                con.execute(
                    """
                    UPDATE positions
                    SET market_slug = ?, outcome = ?, open_shares = ?, avg_entry_price = ?,
                        total_buy_usdc = ?, status = 'open', updated_at = ?
                    WHERE token_id = ?
                    """,
                    (
                        trade.market_slug,
                        trade.outcome,
                        new_shares,
                        avg_price,
                        new_buy,
                        now,
                        trade.token_id,
                    ),
                )
            else:
                con.execute(
                    """
                    INSERT INTO positions(
                        token_id, market_slug, outcome, open_shares, avg_entry_price,
                        total_buy_usdc, total_sell_usdc, status, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 0, 'open', ?)
                    """,
                    (
                        trade.token_id,
                        trade.market_slug,
                        trade.outcome,
                        float(shares),
                        float(price),
                        float(amount_usdc),
                        now,
                    ),
                )
            con.execute(
                """
                INSERT INTO position_events(
                    created_at, trade_id, token_id, side, shares, price, usdc_value, payload_json
                )
                VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?)
                """,
                (
                    now,
                    trade.trade_id,
                    trade.token_id,
                    float(shares),
                    float(price),
                    float(amount_usdc),
                    json.dumps(payload or {}, ensure_ascii=True, default=str),
                ),
            )

    def record_position_sell(
        self,
        trade: WalletTrade,
        shares: float,
        price: float,
        usdc_value: float,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = int(time.time())
        with self._connect() as con:
            row = con.execute(
                "SELECT open_shares, total_sell_usdc FROM positions WHERE token_id = ?",
                (trade.token_id,),
            ).fetchone()
            current_shares = float(row["open_shares"]) if row else 0
            total_sell = float(row["total_sell_usdc"]) if row else 0
            remaining = max(0.0, current_shares - float(shares))
            status = "closed" if remaining <= 0.000001 else "open"
            con.execute(
                """
                UPDATE positions
                SET open_shares = ?, total_sell_usdc = ?, status = ?, updated_at = ?
                WHERE token_id = ?
                """,
                (
                    remaining,
                    total_sell + float(usdc_value),
                    status,
                    now,
                    trade.token_id,
                ),
            )
            con.execute(
                """
                INSERT INTO position_events(
                    created_at, trade_id, token_id, side, shares, price, usdc_value, payload_json
                )
                VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?)
                """,
                (
                    now,
                    trade.trade_id,
                    trade.token_id,
                    float(shares),
                    float(price),
                    float(usdc_value),
                    json.dumps(payload or {}, ensure_ascii=True, default=str),
                ),
            )

    def open_position(self, token_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT * FROM positions
                WHERE token_id = ? AND open_shares > 0 AND status = 'open'
                """,
                (token_id,),
            ).fetchone()
        return dict(row) if row else None

    def positions(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM positions"
        params: tuple = ()
        if not include_closed:
            query += " WHERE open_shares > 0 AND status = 'open'"
        query += " ORDER BY updated_at DESC"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        with self._connect() as con:
            events = con.execute("SELECT COUNT(*) AS count FROM copy_events").fetchone()
            buys = con.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(amount_usdc), 0) AS total FROM copy_events WHERE action IN ('dry_run_buy', 'live_buy')"
            ).fetchone()
            sells = con.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(amount_usdc), 0) AS total FROM copy_events WHERE action IN ('dry_run_sell', 'live_sell')"
            ).fetchone()
            open_positions = con.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(open_shares), 0) AS shares FROM positions WHERE open_shares > 0 AND status = 'open'"
            ).fetchone()
        return {
            "events": int(events["count"] if events else 0),
            "buy_count": int(buys["count"] if buys else 0),
            "buy_usdc": float(buys["total"] if buys else 0),
            "sell_count": int(sells["count"] if sells else 0),
            "sell_usdc": float(sells["total"] if sells else 0),
            "open_positions": int(open_positions["count"] if open_positions else 0),
            "open_shares": float(open_positions["shares"] if open_positions else 0),
        }

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM copy_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json"))
            except json.JSONDecodeError:
                item["payload"] = {}
            events.append(item)
        return events
