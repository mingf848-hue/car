from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from .config import Settings


def _extract_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "activity", "trades", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _trade_key(item: Dict[str, Any]) -> str:
    parts = [
        str(item.get("transactionHash") or item.get("transaction_hash") or item.get("txHash") or item.get("hash") or ""),
        str(item.get("asset") or item.get("token_id") or item.get("tokenId") or ""),
        str(item.get("side") or item.get("tradeSide") or ""),
        str(item.get("timestamp") or item.get("time") or item.get("createdAt") or ""),
        str(item.get("price") or item.get("avgPrice") or ""),
        str(item.get("size") or item.get("amount") or ""),
        str(item.get("slug") or item.get("marketSlug") or item.get("eventSlug") or ""),
        str(item.get("outcome") or item.get("outcomeName") or ""),
    ]
    return "|".join(parts)


def _dedupe_trades(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for item in items:
        key = _trade_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return sorted(unique, key=lambda item: float(item.get("timestamp") or item.get("time") or 0), reverse=True)


class PolymarketPublicClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._market_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    async def fetch_wallet_trades(self, wallet: str, limit: int) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20) as client:
            activity = []
            for side in ("BUY", "SELL"):
                activity.extend(await self._fetch_activity(client, wallet, limit, side=side))
            if activity:
                return _dedupe_trades(activity)[:limit]

            unsided_activity = await self._fetch_activity(client, wallet, limit, side=None)
            if unsided_activity:
                return _dedupe_trades(unsided_activity)[:limit]

            trades = []
            for side in ("BUY", "SELL"):
                trades.extend(await self._fetch_trades(client, wallet, limit, side=side))
            if trades:
                return _dedupe_trades(trades)[:limit]
            return await self._fetch_trades(client, wallet, limit, side=None)

    async def fetch_leaderboard(
        self,
        category: str = "SPORTS",
        time_period: str = "WEEK",
        order_by: str = "PNL",
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        url = self.settings.data_api_host.rstrip("/") + "/v1/leaderboard"
        params = {
            "category": category.upper(),
            "timePeriod": time_period.upper(),
            "orderBy": order_by.upper(),
            "limit": max(1, min(int(limit), 50)),
            "offset": max(0, int(offset)),
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return _extract_list(response.json())

    async def _fetch_activity(
        self,
        client: httpx.AsyncClient,
        wallet: str,
        limit: int,
        side: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        url = self.settings.data_api_host.rstrip("/") + "/activity"
        base_params = {
            "user": wallet,
            "limit": limit,
            "offset": 0,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        for type_value in ("TRADE", ["TRADE"]):
            params = dict(base_params)
            params["type"] = type_value
            if side:
                params["side"] = side
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                items = _extract_list(response.json())
                if items:
                    return items
            except httpx.HTTPError:
                continue
        return []

    async def _fetch_trades(
        self,
        client: httpx.AsyncClient,
        wallet: str,
        limit: int,
        side: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        url = self.settings.data_api_host.rstrip("/") + "/trades"
        params = {
            "user": wallet,
            "limit": limit,
            "offset": 0,
            "takerOnly": "false",
        }
        if side:
            params["side"] = side
        response = await client.get(url, params=params)
        response.raise_for_status()
        return _extract_list(response.json())

    async def fetch_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        if not slug:
            return None
        if slug in self._market_cache:
            return self._market_cache[slug]

        base = self.settings.gamma_api_host.rstrip("/")
        async with httpx.AsyncClient(timeout=20) as client:
            for url, params in (
                (f"{base}/markets/slug/{slug}", None),
                (f"{base}/markets", {"slug": slug}),
            ):
                try:
                    response = await client.get(url, params=params)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    if isinstance(payload, list):
                        market = payload[0] if payload else None
                    elif isinstance(payload, dict) and isinstance(payload.get("markets"), list):
                        market = payload["markets"][0] if payload["markets"] else None
                    elif isinstance(payload, dict):
                        market = payload
                    else:
                        market = None
                    self._market_cache[slug] = market
                    return market
                except httpx.HTTPError:
                    continue

        self._market_cache[slug] = None
        return None

    async def get_price(self, token_id: str, side: str) -> Optional[float]:
        if not token_id:
            return None
        url = self.settings.clob_host.rstrip("/") + "/price"
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url, params={"token_id": token_id, "side": side.upper()})
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict):
            value = payload.get("price")
        else:
            value = payload
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def get_buy_price(self, token_id: str) -> Optional[float]:
        return await self.get_price(token_id, "BUY")

    async def get_sell_price(self, token_id: str) -> Optional[float]:
        return await self.get_price(token_id, "SELL")

    async def geoblock(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.settings.geoblock_url)
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, dict) else {"raw": payload}
