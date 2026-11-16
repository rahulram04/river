"""Trader account and portfolio management."""

from __future__ import annotations

import math
from typing import Any


class Trader:
    def __init__(self, trader_id: str, starting_cash: float = 0.0) -> None:
        if not isinstance(trader_id, str) or not trader_id.strip():
            raise ValueError("trader_id must be a non-empty string")
        self._validate_amount(starting_cash, "starting_cash", allow_zero=True)

        self.trader_id = trader_id
        self.cash = float(starting_cash)
        self.positions: dict[Any, dict[int, float]] = {}

    def deposit(self, amount: float) -> None:
        """Add cash to the account."""
        self._validate_amount(amount, "deposit amount")
        self.cash += amount

    def withdraw(self, amount: float) -> None:
        """Remove cash from the account."""
        self._validate_amount(amount, "withdrawal amount")
        if amount > self.cash:
            raise ValueError("Insufficient funds for withdrawal")
        self.cash -= amount

    def buy(self, market: Any, outcome: int, shares: float) -> float:
        """Buy shares, updating the market and this trader atomically."""
        self._validate_shares(shares)
        cost = market.trade_cost(self._changes(market, outcome, shares))
        if cost > self.cash:
            raise ValueError("Insufficient funds to buy shares")

        paid = market.buy(outcome, shares)
        self.cash -= paid
        market_positions = self.positions.setdefault(market, {})
        market_positions[outcome] = market_positions.get(outcome, 0.0) + shares
        return paid

    def sell(self, market: Any, outcome: int, shares: float) -> float:
        """Sell shares, updating the market and this trader atomically."""
        self._validate_shares(shares)
        market_positions = self.positions.get(market, {})
        owned = market_positions.get(outcome, 0.0)
        if shares > owned:
            raise ValueError("Insufficient shares to sell")

        revenue = market.sell(outcome, shares)
        self.cash += revenue
        remaining = owned - shares
        if remaining == 0:
            del market_positions[outcome]
            if not market_positions:
                del self.positions[market]
        else:
            market_positions[outcome] = remaining
        return revenue

    def position(self, market: Any, outcome: int) -> float:
        """Return the number of shares owned in a market outcome."""
        return self.positions.get(market, {}).get(outcome, 0.0)

    def total_value(self, market: Any) -> float:
        """Return cash plus the current market value of this portfolio."""
        total = self.cash
        prices = market.prices()
        for outcome, shares in self.positions.get(market, {}).items():
            total += shares * prices[outcome]
        return total

    @staticmethod
    def _changes(market: Any, outcome: int, shares: float) -> list[float]:
        changes = [0.0] * market.outcome_count
        changes[outcome] = shares
        return changes

    @staticmethod
    def _validate_amount(
        amount: float, name: str, allow_zero: bool = False
    ) -> None:
        if (
            not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or not math.isfinite(amount)
            or (amount < 0 if allow_zero else amount <= 0)
        ):
            qualifier = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{name} must be a {qualifier} finite number")

    @classmethod
    def _validate_shares(cls, shares: float) -> None:
        cls._validate_amount(shares, "shares")
