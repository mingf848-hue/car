import asyncio
import unittest

from app.config import Settings
from app.recommendations import recommend_wallets


class FakeRecommendationPublic:
    async def fetch_leaderboard(self, category="SPORTS", time_period="WEEK", order_by="PNL", limit=25, offset=0):
        return [
            {
                "proxyWallet": "0x1111111111111111111111111111111111111111",
                "userName": "Sharp Sports",
                "rank": 1,
                "pnl": 2500,
                "vol": 120000,
            },
            {
                "proxyWallet": "0x2222222222222222222222222222222222222222",
                "userName": "Quiet Wallet",
                "rank": 2,
                "pnl": 100,
                "vol": 800,
            },
        ]

    async def fetch_wallet_trades(self, wallet, limit):
        if wallet.endswith("1111"):
            return [
                {
                    "side": "BUY",
                    "asset": "token-a",
                    "timestamp": 1780710000,
                    "price": "0.50",
                    "size": "40",
                    "slug": "nba-finals-game",
                    "title": "Will Team A win the NBA game?",
                    "outcome": "Yes",
                    "profit": "32.5",
                },
                {
                    "side": "SELL",
                    "asset": "token-b",
                    "timestamp": 1780710100,
                    "price": "0.55",
                    "size": "20",
                    "slug": "mlb-total",
                    "title": "MLB total over 7.5?",
                    "outcome": "Over",
                    "realizedPnl": "-5",
                },
            ]
        return []


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class RecommendationTests(unittest.TestCase):
    def test_recommendations_rank_wallets_with_rule_fallback(self):
        result = run(recommend_wallets(Settings(use_deepseek_classifier=False), FakeRecommendationPublic(), limit=2))

        self.assertFalse(result["ai_used"])
        self.assertEqual(result["ai_mode"], "rules")
        self.assertEqual(len(result["wallets"]), 2)
        self.assertEqual(result["wallets"][0]["wallet"], "0x1111111111111111111111111111111111111111")
        self.assertGreater(result["wallets"][0]["score"], result["wallets"][1]["score"])
        self.assertIn("ai_reason", result["wallets"][0])
        self.assertEqual(result["wallets"][0]["buys"], 1)
        self.assertEqual(result["wallets"][0]["sells"], 1)
        self.assertTrue(result["wallets"][0]["recent_pnl_available"])
        self.assertEqual(result["wallets"][0]["recent_pnl"], 27.5)
        self.assertEqual(result["wallets"][0]["recent_pnl_trades"], 2)
        self.assertEqual(result["wallets"][0]["recent_trades"][0]["pnl"], 32.5)


if __name__ == "__main__":
    unittest.main()
