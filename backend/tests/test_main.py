import unittest

from fastapi.testclient import TestClient

from app import main
from app.markets.LMSR import LMSRMarket
from app.models.Users import Trader


class MainApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(main.app)

    def setUp(self) -> None:
        main.markets.clear()
        main.markets["demo"] = LMSRMarket(outcome_count=2, liquidity=10)
        main.traders.clear()
        main.traders["demo"] = Trader("demo", starting_cash=100)

    def test_read_market_returns_prices_and_quantities(self) -> None:
        response = self.client.get("/markets/demo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["market_id"], "demo")
        self.assertEqual(response.json()["outcome_count"], 2)
        self.assertEqual(response.json()["quantities"], [0.0, 0.0])
        self.assertEqual(response.json()["prices"], [0.5, 0.5])

    def test_read_unknown_market_returns_not_found(self) -> None:
        response = self.client.get("/markets/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Market not found")

    def test_create_and_read_trader(self) -> None:
        created = self.client.post(
            "/traders/alice",
            json={"starting_cash": 50},
        )
        read = self.client.get("/traders/alice")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json(), {"trader_id": "alice", "cash": 50.0})
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["cash"], 50.0)
        self.assertEqual(read.json()["positions"], {})

    def test_duplicate_trader_returns_conflict(self) -> None:
        response = self.client.post(
            "/traders/demo",
            json={"starting_cash": 50},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Trader already exists")

    def test_buy_endpoint_updates_market_and_trader(self) -> None:
        response = self.client.post(
            "/markets/demo/buy",
            json={"trader_id": "demo", "outcome": 0, "shares": 1},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["action"], "buy")
        self.assertGreater(body["cost"], 0)
        self.assertEqual(body["quantities"], [1.0, 0.0])
        self.assertEqual(body["positions"], {"0": 1.0})
        self.assertGreater(body["prices"][0], body["prices"][1])

    def test_sell_endpoint_returns_revenue_and_updates_position(self) -> None:
        self.client.post(
            "/markets/demo/buy",
            json={"trader_id": "demo", "outcome": 0, "shares": 1},
        )

        response = self.client.post(
            "/markets/demo/sell",
            json={"trader_id": "demo", "outcome": 0, "shares": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "sell")
        self.assertGreater(response.json()["revenue"], 0)
        self.assertEqual(response.json()["quantities"], [0.0, 0.0])
        self.assertEqual(response.json()["positions"], {})

    def test_trade_with_unknown_trader_returns_not_found(self) -> None:
        response = self.client.post(
            "/markets/demo/buy",
            json={"trader_id": "missing", "outcome": 0, "shares": 1},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Trader not found")

    def test_unaffordable_buy_returns_bad_request_without_mutation(self) -> None:
        main.traders["poor"] = Trader("poor", starting_cash=0)

        response = self.client.post(
            "/markets/demo/buy",
            json={"trader_id": "poor", "outcome": 0, "shares": 1},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Insufficient funds to buy shares")
        self.assertEqual(main.markets["demo"].quantities, (0.0, 0.0))

    def test_invalid_trade_request_returns_validation_error(self) -> None:
        response = self.client.post(
            "/markets/demo/buy",
            json={"trader_id": "demo", "outcome": 0, "shares": 0},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
