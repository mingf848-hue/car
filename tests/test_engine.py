import asyncio
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.engine import CopyTradingEngine
from app.state import StateStore


class FakePublic:
    def __init__(self):
        self.round = 0

    async def geoblock(self):
        return {"blocked": False, "country": "JP"}

    async def fetch_wallet_trades(self, wallet, limit):
        if self.round == 0:
            return [
                {
                    "side": "BUY",
                    "asset": "token-old",
                    "timestamp": 1700000000,
                    "price": "0.50",
                    "size": "10",
                    "slug": "nba-old",
                    "title": "Will Team A win the NBA game?",
                    "outcome": "Yes",
                }
            ]
        if self.round == 1:
            return [
                {
                    "side": "BUY",
                    "asset": "token-new",
                    "timestamp": 1700000100,
                    "price": "0.50",
                    "size": "20",
                    "slug": "nba-new",
                    "title": "Will Team B win the NBA game?",
                    "outcome": "Yes",
                }
            ]
        return [
            {
                "side": "SELL",
                "asset": "token-new",
                "timestamp": 1700000200,
                "price": "0.55",
                "size": "10",
                "slug": "nba-new",
                "title": "Will Team B win the NBA game?",
                "outcome": "Yes",
            }
        ]

    async def fetch_market_by_slug(self, slug):
        return {"slug": slug, "sportsMarketType": "GAME_WINNER"}

    async def get_buy_price(self, token_id):
        return 0.50

    async def get_sell_price(self, token_id):
        return 0.55


class FakeExecutor:
    def __init__(self):
        self.orders = []

    async def market_buy(self, token_id, amount_usdc, price):
        self.orders.append((token_id, amount_usdc, price))
        return {"ok": True}

    async def market_sell(self, token_id, shares, price):
        self.orders.append((token_id, shares, price, "SELL"))
        return {"ok": True}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class EngineTests(unittest.TestCase):
    def test_first_run_warms_seen_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                smart_wallets=("0xabc",),
                sqlite_path=Path(tmp) / "bot.sqlite3",
                copy_amount_usdc=5,
                block_on_geoblock=False,
            )
            public = FakePublic()
            executor = FakeExecutor()
            state = StateStore(settings.sqlite_path)
            engine = CopyTradingEngine(settings, state, public, executor)

            summary = run(engine.run_once())

            self.assertEqual(summary["processed"], 0)
            self.assertEqual(summary["skipped"], 1)
            self.assertEqual(executor.orders, [])

    def test_new_sports_buy_copies_exactly_five_usdc_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                smart_wallets=("0xabc",),
                sqlite_path=Path(tmp) / "bot.sqlite3",
                copy_amount_usdc=5,
                block_on_geoblock=False,
            )
            public = FakePublic()
            executor = FakeExecutor()
            state = StateStore(settings.sqlite_path)
            engine = CopyTradingEngine(settings, state, public, executor)

            run(engine.run_once())
            public.round = 1
            summary = run(engine.run_once())

            self.assertEqual(summary["copied"], 1)
            self.assertEqual(executor.orders, [("token-new", 5.0, 0.50)])
            event = state.recent_events(1)[0]
            self.assertEqual(event["action"], "dry_run_buy")
            self.assertEqual(event["amount_usdc"], 5.0)
            position = state.open_position("token-new")
            self.assertIsNotNone(position)
            self.assertEqual(position["open_shares"], 10.0)

    def test_runtime_followed_wallets_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                smart_wallets=(),
                sqlite_path=Path(tmp) / "bot.sqlite3",
                copy_amount_usdc=5,
                block_on_geoblock=False,
            )
            public = FakePublic()
            public.round = 1
            executor = FakeExecutor()
            state = StateStore(settings.sqlite_path)
            state.upsert_followed_wallet("0xabc", "runtime wallet", "test", active=True)
            engine = CopyTradingEngine(settings, state, public, executor)

            summary = run(engine.run_once())

            self.assertEqual(summary["wallets"], 1)
            self.assertEqual(summary["processed"], 0)
            self.assertEqual(summary["warmup_wallets"], 1)

            public.round = 2
            summary = run(engine.run_once())

            self.assertEqual(summary["wallets"], 1)

    def test_leader_sell_closes_tracked_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                smart_wallets=("0xabc",),
                sqlite_path=Path(tmp) / "bot.sqlite3",
                copy_amount_usdc=5,
                block_on_geoblock=False,
            )
            public = FakePublic()
            executor = FakeExecutor()
            state = StateStore(settings.sqlite_path)
            engine = CopyTradingEngine(settings, state, public, executor)

            run(engine.run_once())
            public.round = 1
            run(engine.run_once())
            public.round = 2
            summary = run(engine.run_once())

            self.assertEqual(summary["copied"], 1)
            self.assertEqual(executor.orders[-1], ("token-new", 10.0, 0.55, "SELL"))
            event = state.recent_events(1)[0]
            self.assertEqual(event["action"], "dry_run_sell")
            self.assertEqual(event["amount_usdc"], 5.5)
            self.assertIsNone(state.open_position("token-new"))

    def test_slippage_guard_skips_trade(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                smart_wallets=("0xabc",),
                sqlite_path=Path(tmp) / "bot.sqlite3",
                copy_amount_usdc=5,
                block_on_geoblock=False,
                copy_historical_on_first_run=True,
                max_slippage_bps=100,
            )
            public = FakePublic()

            async def high_price(token_id):
                return 0.60

            public.get_buy_price = high_price
            executor = FakeExecutor()
            state = StateStore(settings.sqlite_path)
            engine = CopyTradingEngine(settings, state, public, executor)

            summary = run(engine.run_once())

            self.assertEqual(summary["copied"], 0)
            self.assertEqual(state.recent_events(1)[0]["reason"], "slippage_too_high")
            self.assertEqual(executor.orders, [])


if __name__ == "__main__":
    unittest.main()
