import unittest

from app.models import WalletTrade


class WalletTradeTests(unittest.TestCase):
    def test_wallet_trade_parses_activity_shape(self):
        trade = WalletTrade.from_activity(
            "0xabc",
            {
                "side": "BUY",
                "asset": "123",
                "transactionHash": "0xtx",
                "timestamp": 1700000000000,
                "price": "0.25",
                "size": "20",
                "slug": "nba-finals-lakers",
                "title": "Will the Lakers win the NBA Finals?",
                "outcome": "Yes",
            },
        )

        self.assertEqual(trade.side, "BUY")
        self.assertEqual(trade.token_id, "123")
        self.assertEqual(trade.usdc_size, 5.0)
        self.assertEqual(trade.timestamp, 1700000000)
        self.assertTrue(trade.trade_id)


if __name__ == "__main__":
    unittest.main()
