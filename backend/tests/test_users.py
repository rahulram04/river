import unittest

from app.markets.LMSR import LMSRMarket
from app.models.Users import Trader


class TraderTests(unittest.TestCase):
    def test_buy_updates_cash_and_market_specific_position(self) -> None:
        market = LMSRMarket(2, 10)
        trader = Trader("alice", 100)

        paid = trader.buy(market, 0, 2)

        self.assertAlmostEqual(trader.cash, 100 - paid)
        self.assertEqual(trader.position(market, 0), 2)
        self.assertEqual(trader.position(market, 1), 0)

    def test_unaffordable_buy_does_not_change_market_or_portfolio(self) -> None:
        market = LMSRMarket(2, 10)
        trader = Trader("alice", 0)

        with self.assertRaises(ValueError):
            trader.buy(market, 0, 1)

        self.assertEqual(market.quantities, (0.0, 0.0))
        self.assertEqual(trader.position(market, 0), 0)

    def test_positions_are_separate_for_each_market(self) -> None:
        first_market = LMSRMarket(2, 10)
        second_market = LMSRMarket(2, 10)
        trader = Trader("alice", 100)

        trader.buy(first_market, 0, 1)
        trader.buy(second_market, 0, 2)

        self.assertEqual(trader.position(first_market, 0), 1)
        self.assertEqual(trader.position(second_market, 0), 2)

    def test_sell_updates_cash_and_removes_empty_position(self) -> None:
        market = LMSRMarket(2, 10)
        trader = Trader("alice", 100)
        trader.buy(market, 0, 2)
        cash_after_buy = trader.cash

        revenue = trader.sell(market, 0, 2)

        self.assertAlmostEqual(trader.cash, cash_after_buy + revenue)
        self.assertEqual(trader.position(market, 0), 0)

    def test_rejects_invalid_amounts(self) -> None:
        with self.assertRaises(ValueError):
            Trader("alice", -1)
        with self.assertRaises(ValueError):
            Trader("alice", 1).deposit(float("nan"))


if __name__ == "__main__":
    unittest.main()
