from __future__ import annotations

from typing import Any, Dict, Optional

from .config import Settings


class DryRunExecutor:
    async def market_buy(self, token_id: str, amount_usdc: float, price: Optional[float]) -> Dict[str, Any]:
        return {
            "dry_run": True,
            "side": "BUY",
            "token_id": token_id,
            "amount_usdc": amount_usdc,
            "price": price,
        }

    async def market_sell(self, token_id: str, shares: float, price: Optional[float]) -> Dict[str, Any]:
        return {
            "dry_run": True,
            "side": "SELL",
            "token_id": token_id,
            "shares": shares,
            "price": price,
        }


class LiveClobExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.polymarket_private_key:
            raise ValueError("POLYMARKET_PRIVATE_KEY is required for EXECUTION_MODE=live")

        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds

        creds = None
        if settings.clob_api_key and settings.clob_api_secret and settings.clob_api_passphrase:
            creds = ApiCreds(
                api_key=settings.clob_api_key,
                api_secret=settings.clob_api_secret,
                api_passphrase=settings.clob_api_passphrase,
            )

        self._sdk = self._load_sdk_symbols()
        self.client = ClobClient(
            host=settings.clob_host,
            chain_id=settings.chain_id,
            key=settings.polymarket_private_key,
            creds=creds,
            signature_type=settings.polymarket_signature_type,
            funder=settings.polymarket_funder or None,
            retry_on_error=True,
        )
        if creds is None and settings.derive_api_key_if_missing:
            self.client.set_api_creds(self.client.create_or_derive_api_key())
        if self.client.creds is None:
            raise ValueError("CLOB API credentials are required for live order posting")

    @staticmethod
    def _load_sdk_symbols() -> Dict[str, Any]:
        from py_clob_client_v2.clob_types import MarketOrderArgs, OrderType

        return {
            "MarketOrderArgs": MarketOrderArgs,
            "OrderType": OrderType,
        }

    async def market_buy(self, token_id: str, amount_usdc: float, price: Optional[float]) -> Dict[str, Any]:
        MarketOrderArgs = self._sdk["MarketOrderArgs"]
        OrderType = self._sdk["OrderType"]
        order = MarketOrderArgs(
            token_id=token_id,
            amount=float(amount_usdc),
            side="BUY",
            price=float(price or 0),
        )
        response = self.client.create_and_post_market_order(order, order_type=OrderType.FOK)
        return response if isinstance(response, dict) else {"response": response}

    async def market_sell(self, token_id: str, shares: float, price: Optional[float]) -> Dict[str, Any]:
        MarketOrderArgs = self._sdk["MarketOrderArgs"]
        OrderType = self._sdk["OrderType"]
        order = MarketOrderArgs(
            token_id=token_id,
            amount=float(shares),
            side="SELL",
            price=float(price or 0),
        )
        response = self.client.create_and_post_market_order(order, order_type=OrderType.FOK)
        return response if isinstance(response, dict) else {"response": response}


def build_executor(settings: Settings):
    if settings.live_trading_enabled:
        return LiveClobExecutor(settings)
    return DryRunExecutor()
