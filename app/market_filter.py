from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .config import Settings
from .models import WalletTrade


SPORTS_KEYWORDS = {
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "wnba",
    "ufc",
    "mma",
    "boxing",
    "soccer",
    "football",
    "tennis",
    "golf",
    "formula 1",
    "f1",
    "nascar",
    "cricket",
    "rugby",
    "premier league",
    "champions league",
    "world cup",
    "ncaa",
    "march madness",
    "olympics",
    "atp",
    "wta",
    "super bowl",
    "world series",
    "stanley cup",
}


def _flatten_market_text(market: Dict[str, Any]) -> str:
    parts = []
    for key in (
        "question",
        "title",
        "slug",
        "eventSlug",
        "category",
        "subcategory",
        "sport",
        "league",
        "tournament",
        "sportsMarketType",
        "sportsMarketGroup",
    ):
        value = market.get(key)
        if isinstance(value, str):
            parts.append(value)
    tags = market.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                parts.extend(str(tag.get(k, "")) for k in ("label", "name", "slug"))
            else:
                parts.append(str(tag))
    return " ".join(parts).lower()


def looks_like_sports(trade: WalletTrade, market: Optional[Dict[str, Any]]) -> bool:
    if market:
        for key in ("sportsMarketType", "sportsMarketGroup", "sport", "league", "gameId"):
            if market.get(key):
                return True
        text = _flatten_market_text(market)
    else:
        text = ""
    text = f"{text} {trade.market_title} {trade.market_slug}".lower()
    normalized = re.sub(r"[-_/]+", " ", text)
    return any(keyword in normalized for keyword in SPORTS_KEYWORDS)


class DeepSeekSportsClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def classify(self, trade: WalletTrade, market: Optional[Dict[str, Any]]) -> Optional[bool]:
        if not (self.settings.use_deepseek_classifier and self.settings.deepseek_api_key):
            return None

        try:
            import httpx
        except ImportError:
            return None

        prompt = {
            "task": "Classify whether this Polymarket prediction market is about a sports event or sports outcome.",
            "return": {"sports": "boolean"},
            "market_title": trade.market_title,
            "market_slug": trade.market_slug,
            "outcome": trade.outcome,
            "market_fields": market or {},
        }
        url = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.deepseek_api_key}"}
        body = {
            "model": self.settings.deepseek_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "Reply with strict JSON only. No markdown.",
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=False),
                },
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed.get("sports"), bool):
                return parsed["sports"]
        except Exception:
            return None
        return None
