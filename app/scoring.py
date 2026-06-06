from __future__ import annotations

import time
from typing import Any, Dict, List

from .config import Settings
from .market_filter import looks_like_sports
from .models import WalletTrade
from .pnl import extract_pnl


def _pnl_from_raw(raw: Dict[str, Any]) -> float:
    value, available, _ = extract_pnl(raw)
    if available:
        return value
    return 0.0


async def score_wallet(settings: Settings, public_client: Any, wallet: str) -> Dict[str, Any]:
    raw_trades = await public_client.fetch_wallet_trades(wallet, settings.activity_limit)
    trades = [WalletTrade.from_activity(wallet, raw) for raw in raw_trades]
    trades = [trade for trade in trades if trade.token_id]
    if not trades:
        return {
            "wallet": wallet,
            "score": 0,
            "reason": "no_recent_trades",
            "trades": 0,
            "sports_ratio": 0,
            "estimated_pnl": 0,
        }

    now = int(time.time())
    sports_count = 0
    total_notional = 0.0
    pnl = 0.0
    newest_age_hours = 9999.0

    for trade in trades:
        market = await public_client.fetch_market_by_slug(trade.market_slug) if trade.market_slug else None
        if looks_like_sports(trade, market):
            sports_count += 1
        total_notional += trade.usdc_size
        pnl += _pnl_from_raw(trade.raw)
        newest_age_hours = min(newest_age_hours, max(0, now - trade.timestamp) / 3600)

    sports_ratio = sports_count / len(trades)
    activity_score = min(len(trades) / 30, 1) * 20
    sports_score = sports_ratio * 45
    notional_score = min(total_notional / 1000, 1) * 15
    freshness_score = max(0, 1 - newest_age_hours / (24 * 7)) * 10
    pnl_score = max(-10, min(10, pnl / 100))
    score = round(activity_score + sports_score + notional_score + freshness_score + pnl_score, 2)

    return {
        "wallet": wallet,
        "score": score,
        "trades": len(trades),
        "sports_ratio": round(sports_ratio, 4),
        "total_notional": round(total_notional, 2),
        "estimated_pnl": round(pnl, 2),
        "newest_age_hours": round(newest_age_hours, 2),
    }


async def score_wallets(settings: Settings, public_client: Any, wallets: List[str]) -> List[Dict[str, Any]]:
    results = []
    for wallet in wallets:
        results.append(await score_wallet(settings, public_client, wallet))
    return sorted(results, key=lambda item: item["score"], reverse=True)
