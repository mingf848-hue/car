from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .config import Settings
from .market_filter import looks_like_sports
from .models import WalletTrade
from .pnl import extract_pnl
from .translation import translate_market, translate_outcome


def _float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _leader_wallet(item: Dict[str, Any]) -> str:
    return str(item.get("proxyWallet") or item.get("proxy_wallet") or item.get("wallet") or "").lower()


def _leader_name(item: Dict[str, Any], wallet: str) -> str:
    return str(item.get("userName") or item.get("username") or item.get("name") or wallet[:10])


def _leader_pnl(item: Dict[str, Any]) -> float:
    for key in ("pnl", "profit", "realizedPnl", "realizedPnL", "netPnl"):
        value = _float(item.get(key))
        if value:
            return value
    return 0.0


def _leader_volume(item: Dict[str, Any]) -> float:
    for key in ("vol", "volume", "totalVolume", "amount"):
        value = _float(item.get(key))
        if value:
            return value
    return 0.0


def _rule_reason(
    score: float,
    sports_ratio: float,
    trades: int,
    newest_age_hours: float,
    pnl: float,
    recent_pnl: float,
    recent_pnl_available: bool,
) -> str:
    if trades == 0:
        return "近期没有公开下注记录，暂不建议直接跟单。"
    if recent_pnl_available and recent_pnl < 0:
        return "近期公开盈亏为负，建议先观察下注质量，不要直接跟重仓。"
    if recent_pnl_available and recent_pnl > 0 and score >= 76:
        return "榜单盈利和近期公开盈亏都为正，适合作为优先观察钱包。"
    if score >= 78:
        return "盈利、活跃度和体育占比都靠前，适合作为优先观察钱包。"
    if sports_ratio < 0.55:
        return "近期交易里体育占比偏低，建议只观察体育单。"
    if newest_age_hours > 72:
        return "近期活跃度下降，适合先加入观察而不是立即重仓。"
    if not recent_pnl_available:
        return "接口未返回近期盈亏，建议打开下注详情核对单子质量。"
    if pnl <= 0:
        return "近期盈利不突出，建议结合下注详情再决定。"
    return "指标中等，适合查看下注详情后再跟单。"


def _rule_risk(sports_ratio: float, trades: int, newest_age_hours: float) -> str:
    if trades == 0:
        return "无近期公开交易。"
    if sports_ratio < 0.55:
        return "体育相关度偏低。"
    if newest_age_hours > 72:
        return "最近活跃度不足。"
    return "仍需注意滑点和单场集中风险。"


def _score_candidate(
    leader: Dict[str, Any],
    wallet: str,
    trades: List[WalletTrade],
    now: int,
) -> Dict[str, Any]:
    pnl = _leader_pnl(leader)
    volume = _leader_volume(leader)
    buys = sum(1 for trade in trades if trade.side == "BUY")
    sells = sum(1 for trade in trades if trade.side == "SELL")
    total_notional = round(sum(trade.usdc_size for trade in trades), 2)
    newest_age_hours = 9999.0
    sports_count = 0
    recent_pnl = 0.0
    recent_pnl_trades = 0
    for trade in trades:
        newest_age_hours = min(newest_age_hours, max(0, now - trade.timestamp) / 3600)
        if looks_like_sports(trade, None):
            sports_count += 1
        trade_pnl, has_pnl, _ = extract_pnl(trade.raw)
        if has_pnl:
            recent_pnl += trade_pnl
            recent_pnl_trades += 1

    if not trades:
        newest_age_hours = 9999.0
    sports_ratio = sports_count / len(trades) if trades else 0.0
    activity_score = min(len(trades) / 30, 1) * 22
    sports_score = sports_ratio * 26
    freshness_score = max(0, 1 - newest_age_hours / (24 * 7)) * 16
    pnl_score = max(-10, min(12, pnl / 300))
    recent_pnl_score = max(-16, min(22, recent_pnl / 50)) if recent_pnl_trades else 0
    volume_score = min(volume / 50_000, 1) * 10
    score = round(
        max(0, min(100, activity_score + sports_score + freshness_score + pnl_score + recent_pnl_score + volume_score)),
        1,
    )
    sample_trades = []
    for trade in trades[:3]:
        trade_pnl, has_pnl, _ = extract_pnl(trade.raw)
        sample_trades.append(
            {
                "timestamp": trade.timestamp,
                "side": trade.side,
                "market_title": trade.market_title,
                "market_title_zh": translate_market(trade.market_slug, trade.market_title),
                "market_slug": trade.market_slug,
                "outcome": trade.outcome,
                "outcome_zh": translate_outcome(trade.outcome),
                "price": trade.price,
                "size": trade.size,
                "usdc_size": round(trade.usdc_size, 2),
                "pnl": round(trade_pnl, 2) if has_pnl else None,
                "pnl_available": has_pnl,
            }
        )
    return {
        "wallet": wallet,
        "label": _leader_name(leader, wallet),
        "rank": leader.get("rank"),
        "leaderboard_pnl": round(pnl, 2),
        "leaderboard_volume": round(volume, 2),
        "recent_pnl": round(recent_pnl, 2),
        "recent_pnl_available": bool(recent_pnl_trades),
        "recent_pnl_trades": recent_pnl_trades,
        "score": score,
        "trades": len(trades),
        "buys": buys,
        "sells": sells,
        "sports_ratio": round(sports_ratio, 4),
        "total_notional": total_notional,
        "newest_age_hours": round(newest_age_hours, 2),
        "ai_label": "规则推荐",
        "ai_reason": _rule_reason(
            score,
            sports_ratio,
            len(trades),
            newest_age_hours,
            pnl,
            recent_pnl,
            bool(recent_pnl_trades),
        ),
        "risk": _rule_risk(sports_ratio, len(trades), newest_age_hours),
        "recent_trades": sample_trades,
        "raw": leader,
    }


async def _deepseek_notes(settings: Settings, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Dict[str, str]]]:
    if not (settings.use_deepseek_classifier and settings.deepseek_api_key and candidates):
        return None
    try:
        import httpx
    except ImportError:
        return None

    payload = {
        "task": "Pick the best Polymarket sports copy-trading wallets from scored candidates.",
        "return": "Strict JSON object: {\"recommendations\":[{\"wallet\":\"0x...\",\"label\":\"优先/观察/谨慎\",\"reason\":\"中文一句话\",\"risk\":\"中文一句话\"}]}",
        "rules": [
            "Prefer profitable, active, sports-heavy wallets.",
            "Do not invent data beyond the metrics.",
            "Be concise and practical for a mobile trading app.",
        ],
        "candidates": [
            {
                "wallet": item["wallet"],
                "label": item["label"],
                "score": item["score"],
                "pnl": item["leaderboard_pnl"],
                "recent_pnl": item["recent_pnl"],
                "recent_pnl_available": item["recent_pnl_available"],
                "volume": item["leaderboard_volume"],
                "trades": item["trades"],
                "sports_ratio": item["sports_ratio"],
                "newest_age_hours": item["newest_age_hours"],
                "recent_trades": item["recent_trades"],
            }
            for item in candidates[:8]
        ],
    }
    body = {
        "model": settings.deepseek_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": "你是交易风控助手。只返回严格 JSON，不要 markdown。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=16) as client:
            response = await client.post(
                settings.deepseek_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json=body,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        notes: Dict[str, Dict[str, str]] = {}
        for item in parsed.get("recommendations", []):
            wallet = str(item.get("wallet") or "").lower()
            if wallet:
                notes[wallet] = {
                    "ai_label": str(item.get("label") or "AI 推荐"),
                    "ai_reason": str(item.get("reason") or ""),
                    "risk": str(item.get("risk") or ""),
                }
        return notes
    except Exception:
        return None


async def recommend_wallets(settings: Settings, public_client: Any, limit: int = 12) -> Dict[str, Any]:
    leaders = await public_client.fetch_leaderboard(
        category="SPORTS",
        time_period="WEEK",
        order_by="PNL",
        limit=max(5, min(int(limit), 30)),
    )
    now = int(time.time())
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for leader in leaders:
        wallet = _leader_wallet(leader)
        if not wallet or wallet in seen:
            continue
        seen.add(wallet)
        try:
            raw_trades = await public_client.fetch_wallet_trades(wallet, min(settings.activity_limit, 30))
        except Exception:
            raw_trades = []
        trades = [WalletTrade.from_activity(wallet, raw) for raw in raw_trades]
        trades = [trade for trade in trades if trade.token_id]
        candidates.append(_score_candidate(leader, wallet, trades, now))

    candidates.sort(key=lambda item: item["score"], reverse=True)
    notes = await _deepseek_notes(settings, candidates)
    ai_used = bool(notes)
    if notes:
        for item in candidates:
            note = notes.get(item["wallet"])
            if not note:
                continue
            item["ai_label"] = note.get("ai_label") or item["ai_label"]
            item["ai_reason"] = note.get("ai_reason") or item["ai_reason"]
            item["risk"] = note.get("risk") or item["risk"]

    return {
        "ai_used": ai_used,
        "ai_mode": "deepseek" if ai_used else "rules",
        "wallets": candidates[:limit],
    }
