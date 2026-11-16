import math
import unittest

from app.markets.LMSR import LMSRMarket


class LMSRMarketTests(unittest.TestCase):
    def test_initial_prices_are_uniform(self) -> None:
        market = LMSRMarket(outcome_count=3, liquidity=10)

        self.assertEqual(market.quantities, (0.0, 0.0, 0.0))
        self.assertEqual(market.prices(), (1 / 3, 1 / 3, 1 / 3))

    def test_buy_updates_quantities_and_prices(self) -> None:
        market = LMSRMarket(outcome_count=2, liquidity=10)

        paid = market.buy(0, 1)

        self.assertGreater(paid, 0)
        self.assertEqual(market.quantities, (1.0, 0.0))
        self.assertGreater(market.prices()[0], market.prices()[1])
        self.assertAlmostEqual(sum(market.prices()), 1.0)

    def test_trade_cost_does_not_mutate_market(self) -> None:
        market = LMSRMarket(outcome_count=2, liquidity=10)
        original_quantities = market.quantities

        cost = market.trade_cost((2, 0))

        self.assertGreater(cost, 0)
        self.assertEqual(market.quantities, original_quantities)

    def test_buy_then_sell_returns_inverse_cost(self) -> None:
        market = LMSRMarket(outcome_count=2, liquidity=10)
        paid = market.buy(0, 2)
        received = market.sell(0, 2)

        self.assertAlmostEqual(paid, received)
        self.assertEqual(market.quantities, (0.0, 0.0))

    def test_large_quantities_are_numerically_stable(self) -> None:
        market = LMSRMarket(outcome_count=2, liquidity=1)

        market.buy(0, 10_000)

        prices = market.prices()
        self.assertTrue(math.isfinite(market.cost()))
        self.assertAlmostEqual(prices[0], 1.0)
        self.assertAlmostEqual(prices[1], 0.0)

    def test_rejects_invalid_trades(self) -> None:
        market = LMSRMarket(outcome_count=2, liquidity=10)

        with self.assertRaises(ValueError):
            market.buy(0, 0)
        with self.assertRaises(IndexError):
            market.buy(2, 1)
        with self.assertRaises(ValueError):
            market.sell(0, 1)
        with self.assertRaises(ValueError):
            market.trade_cost((1,))


if __name__ == "__main__":
    unittest.main()
