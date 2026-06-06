from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .config import Settings
from .market_filter import DeepSeekSportsClassifier, looks_like_sports
from .models import CopyResult, WalletTrade
from .state import StateStore


class CopyTradingEngine:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        public_client: Any,
        executor: Any,
        classifier: Optional[DeepSeekSportsClassifier] = None,
    ):
        self.settings = settings
        self.state = state
        self.public = public_client
        self.executor = executor
        self.classifier = classifier or DeepSeekSportsClassifier(settings)

    async def run_once(self) -> Dict[str, Any]:
        summary = {
            "started_at": int(time.time()),
            "wallets": len(self.settings.smart_wallets),
            "fetched": 0,
            "warmed_up": 0,
            "warmup_wallets": 0,
            "processed": 0,
            "copied": 0,
            "skipped": 0,
            "blocked": False,
            "errors": [],
        }

        if not self.settings.smart_wallets:
            result = CopyResult(
                trade=None,
                action="config_error",
                reason="未配置 SMART_WALLETS，请在 Zeabur Variables 里填写要跟踪的钱包地址",
            )
            self.state.record_result(result)
            summary["errors"].append(result.reason)
            return summary

        if self.settings.block_on_geoblock:
            try:
                block_result = await self.public.geoblock()
                blocked_reason = self._blocked_reason(block_result)
                if blocked_reason:
                    result = CopyResult(
                        trade=None,
                        action="blocked",
                        reason=blocked_reason,
                        payload={"geoblock": block_result},
                    )
                    self.state.record_result(result)
                    summary["blocked"] = True
                    summary["errors"].append(blocked_reason)
                    return summary
            except Exception as exc:
                summary["errors"].append(f"geoblock_check_failed: {exc}")
                return summary

        for wallet in self.settings.smart_wallets:
            try:
                raw_trades = await self.public.fetch_wallet_trades(wallet, self.settings.activity_limit)
            except Exception as exc:
                summary["errors"].append(f"{wallet}: fetch_failed: {exc}")
                continue

            trades = [WalletTrade.from_activity(wallet, raw) for raw in raw_trades]
            trades = [trade for trade in trades if trade.token_id and trade.side]
            trades.sort(key=lambda item: item.timestamp)
            summary["fetched"] += len(trades)

            if not self.state.is_wallet_initialized(wallet):
                if not self.settings.copy_historical_on_first_run:
                    for trade in trades:
                        self.state.mark_seen(trade)
                    self.state.initialize_wallet(wallet)
                    if not trades:
                        self.state.record_result(
                            CopyResult(
                                trade=None,
                                action="warmup",
                                reason="首次扫描已完成：这个钱包近期没有读取到可跟踪交易，请确认地址是 Polymarket 钱包且近期有交易",
                                payload={"wallet": wallet, "seen_trades": 0},
                            )
                        )
                    else:
                        self.state.record_result(
                            CopyResult(
                                trade=None,
                                action="warmup",
                                reason="首次扫描已完成预热：历史交易只记录不跟单，之后的新交易才会触发跟买/跟卖",
                                payload={"wallet": wallet, "seen_trades": len(trades)},
                            )
                        )
                    summary["warmup_wallets"] += 1
                    summary["warmed_up"] += len(trades)
                    summary["skipped"] += len(trades)
                    continue
                self.state.initialize_wallet(wallet)

            for trade in trades:
                if self.state.has_seen(trade.trade_id):
                    continue
                result = await self._handle_trade(trade)
                self.state.record_result(result)
                self.state.mark_seen(trade)
                summary["processed"] += 1
                if result.action in {"dry_run_buy", "live_buy", "dry_run_sell", "live_sell"}:
                    summary["copied"] += 1
                else:
                    summary["skipped"] += 1

        return summary

    def _blocked_reason(self, payload: Dict[str, Any]) -> Optional[str]:
        blocked = bool(
            payload.get("blocked")
            or payload.get("isBlocked")
            or payload.get("geoblocked")
            or payload.get("is_geoblocked")
        )
        country = str(
            payload.get("country")
            or payload.get("countryCode")
            or payload.get("country_code")
            or ""
        ).upper()
        if blocked:
            return f"polymarket_geoblocked_{country or 'unknown'}"
        if country in {code.upper() for code in self.settings.close_only_country_codes}:
            return f"polymarket_close_only_{country}"
        return None

    async def _handle_trade(self, trade: WalletTrade) -> CopyResult:
        if trade.side == "BUY":
            return await self._handle_buy(trade)
        if trade.side == "SELL":
            return await self._handle_sell(trade)
        return CopyResult(trade=trade, action="skip", reason="unsupported_leader_side")

    async def _handle_buy(self, trade: WalletTrade) -> CopyResult:
        if trade.usdc_size < self.settings.min_leader_usdc_size:
            return CopyResult(
                trade=trade,
                action="skip",
                reason="leader_trade_too_small",
                payload={"leader_usdc_size": trade.usdc_size},
            )

        if self.state.token_on_cooldown(trade.token_id, self.settings.cooldown_seconds_per_token):
            return CopyResult(trade=trade, action="skip", reason="token_on_cooldown")

        market = None
        if trade.market_slug:
            market = await self.public.fetch_market_by_slug(trade.market_slug)

        if self.settings.sports_only and not await self._is_sports_trade(trade, market):
            return CopyResult(trade=trade, action="skip", reason="not_sports_market")

        current_price = None
        if self.settings.require_price_check:
            try:
                current_price = await self.public.get_buy_price(trade.token_id)
            except Exception as exc:
                return CopyResult(
                    trade=trade,
                    action="skip",
                    reason="price_check_failed",
                    payload={"error": str(exc)},
                )
            if current_price is None:
                return CopyResult(trade=trade, action="skip", reason="missing_current_price")
            if trade.price:
                max_price = min(0.99, trade.price * (1 + self.settings.max_slippage_bps / 10_000))
                if current_price > max_price:
                    return CopyResult(
                        trade=trade,
                        action="skip",
                        reason="slippage_too_high",
                        payload={
                            "leader_price": trade.price,
                            "current_price": current_price,
                            "max_price": max_price,
                        },
                    )

        amount = round(float(self.settings.copy_amount_usdc), 2)
        if self.settings.live_trading_enabled:
            live_spend = self.state.live_spend_today()
            if live_spend + amount > self.settings.max_live_daily_usdc:
                return CopyResult(
                    trade=trade,
                    action="skip",
                    reason="daily_live_limit_reached",
                    payload={"live_spend_today": live_spend},
                )

        response = await self.executor.market_buy(trade.token_id, amount, current_price)
        action = "live_buy" if self.settings.live_trading_enabled else "dry_run_buy"
        entry_price = current_price or trade.price
        shares = amount / entry_price if entry_price else 0.0
        self.state.record_position_buy(
            trade=trade,
            amount_usdc=amount,
            shares=shares,
            price=entry_price or 0.0,
            payload={"order": response, "mode": self.settings.execution_mode},
        )
        self.state.touch_token_cooldown(trade.token_id)
        return CopyResult(
            trade=trade,
            action=action,
            reason=f"copied_fixed_{amount:.2f}_usdc",
            amount_usdc=amount,
            payload={
                "leader_wallet": trade.wallet,
                "leader_price": trade.price,
                "current_price": current_price,
                "market": trade.market_title,
                "slug": trade.market_slug,
                "outcome": trade.outcome,
                "estimated_shares": shares,
                "order": response,
            },
        )

    async def _handle_sell(self, trade: WalletTrade) -> CopyResult:
        if not self.settings.auto_follow_sells:
            return CopyResult(trade=trade, action="skip", reason="auto_follow_sells_disabled")

        position = self.state.open_position(trade.token_id)
        if not position:
            return CopyResult(trade=trade, action="skip", reason="no_tracked_position_to_sell")

        shares = float(position["open_shares"])
        if shares < self.settings.min_sell_shares:
            return CopyResult(
                trade=trade,
                action="skip",
                reason="tracked_position_below_min_sell_shares",
                payload={"open_shares": shares},
            )

        if self.settings.sell_mode != "close_full_on_leader_sell":
            return CopyResult(
                trade=trade,
                action="skip",
                reason="unsupported_sell_mode",
                payload={"sell_mode": self.settings.sell_mode},
            )

        current_price = None
        if self.settings.require_price_check:
            try:
                current_price = await self.public.get_sell_price(trade.token_id)
            except Exception as exc:
                return CopyResult(
                    trade=trade,
                    action="skip",
                    reason="sell_price_check_failed",
                    payload={"error": str(exc)},
                )
            if current_price is None:
                return CopyResult(trade=trade, action="skip", reason="missing_current_sell_price")
            if trade.price:
                min_price = max(0.01, trade.price * (1 - self.settings.max_slippage_bps / 10_000))
                if current_price < min_price:
                    return CopyResult(
                        trade=trade,
                        action="skip",
                        reason="sell_slippage_too_high",
                        payload={
                            "leader_price": trade.price,
                            "current_price": current_price,
                            "min_price": min_price,
                        },
                    )

        response = await self.executor.market_sell(trade.token_id, shares, current_price)
        action = "live_sell" if self.settings.live_trading_enabled else "dry_run_sell"
        sell_price = current_price or trade.price or 0.0
        sell_usdc = round(shares * sell_price, 2)
        self.state.record_position_sell(
            trade=trade,
            shares=shares,
            price=sell_price,
            usdc_value=sell_usdc,
            payload={"order": response, "mode": self.settings.execution_mode},
        )
        return CopyResult(
            trade=trade,
            action=action,
            reason=f"closed_tracked_position_{shares:.4f}_shares",
            amount_usdc=sell_usdc,
            payload={
                "leader_wallet": trade.wallet,
                "leader_price": trade.price,
                "current_price": current_price,
                "market": trade.market_title,
                "slug": trade.market_slug,
                "outcome": trade.outcome,
                "shares_sold": shares,
                "position_before": position,
                "order": response,
            },
        )

    async def _is_sports_trade(self, trade: WalletTrade, market: Optional[Dict[str, Any]]) -> bool:
        is_sports = looks_like_sports(trade, market)
        if not is_sports:
            classified = await self.classifier.classify(trade, market)
            is_sports = bool(classified)
        return is_sports
