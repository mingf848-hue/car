from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _first(raw: Dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in raw and raw[name] not in (None, ""):
            return raw[name]
    return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_ts(value: Any) -> int:
    try:
        ts = int(float(value))
    except (TypeError, ValueError):
        return int(time.time())
    if ts > 10_000_000_000:
        return ts // 1000
    return ts


@dataclass(frozen=True)
class WalletTrade:
    wallet: str
    trade_id: str
    tx_hash: str
    timestamp: int
    side: str
    token_id: str
    condition_id: str
    market_slug: str
    market_title: str
    outcome: str
    price: float
    size: float
    usdc_size: float
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_activity(cls, wallet: str, raw: Dict[str, Any]) -> "WalletTrade":
        side = str(
            _first(
                raw,
                "side",
                "tradeSide",
                "trade_side",
                "takerSide",
                "makerSide",
                "type",
                default="",
            )
        ).upper()
        if side not in {"BUY", "SELL"}:
            side = "BUY" if "buy" in side.lower() else ("SELL" if "sell" in side.lower() else side)

        token_id = str(_first(raw, "asset", "token_id", "tokenId", "outcomeTokenId", default=""))
        tx_hash = str(_first(raw, "transactionHash", "transaction_hash", "txHash", "hash", default=""))
        timestamp = _int_ts(_first(raw, "timestamp", "time", "createdAt", default=time.time()))
        price = _float(_first(raw, "price", "avgPrice", "averagePrice"))
        size = _float(_first(raw, "size", "amount", "shares"))
        usdc_size = _float(_first(raw, "usdcSize", "usdSize", "value", "notional"))
        if not usdc_size and price and size:
            usdc_size = price * size

        market_slug = str(_first(raw, "slug", "marketSlug", "market_slug", "eventSlug", default=""))
        market_title = str(_first(raw, "title", "marketTitle", "eventTitle", "question", default=""))
        outcome = str(_first(raw, "outcome", "outcomeName", "name", default=""))
        condition_id = str(_first(raw, "conditionId", "condition_id", default=""))

        stable_parts = [
            wallet.lower(),
            tx_hash,
            token_id,
            side,
            str(timestamp),
            f"{price:.8f}",
            f"{size:.8f}",
            market_slug,
            outcome,
        ]
        trade_id = hashlib.sha1("|".join(stable_parts).encode("utf-8")).hexdigest()
        return cls(
            wallet=wallet,
            trade_id=trade_id,
            tx_hash=tx_hash,
            timestamp=timestamp,
            side=side,
            token_id=token_id,
            condition_id=condition_id,
            market_slug=market_slug,
            market_title=market_title,
            outcome=outcome,
            price=price,
            size=size,
            usdc_size=usdc_size,
            raw=raw,
        )


@dataclass
class CopyResult:
    trade: Optional[WalletTrade]
    action: str
    reason: str
    amount_usdc: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)
