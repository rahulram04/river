"""Logarithmic Market Scoring Rule (LMSR) market."""

from __future__ import annotations

import math
from collections.abc import Iterable


class LMSRMarket:
    """A cost-function LMSR market for mutually exclusive outcomes.

    The market uses the cost function

        C(q) = b * log(sum(exp(q_i / b)))

    where ``q_i`` is the number of shares outstanding for outcome ``i`` and
    ``b`` is the liquidity parameter.
    """

    def __init__(
        self,
        outcome_count: int,
        liquidity: float,
        quantities: Iterable[float] | None = None,
    ) -> None:
        if not isinstance(outcome_count, int) or isinstance(outcome_count, bool):
            raise TypeError("outcome_count must be an integer")
        if outcome_count < 2:
            raise ValueError("outcome_count must be at least 2")
        if not math.isfinite(liquidity) or liquidity <= 0:
            raise ValueError("liquidity must be a positive finite number")

        initial_quantities = (
            [0.0] * outcome_count
            if quantities is None
            else self._validate_vector(quantities, outcome_count, "quantities")
        )

        self._outcome_count = outcome_count
        self._liquidity = float(liquidity)
        self._quantities = initial_quantities

    @property
    def outcome_count(self) -> int:
        return self._outcome_count

    @property
    def liquidity(self) -> float:
        return self._liquidity

    @property
    def quantities(self) -> tuple[float, ...]:
        """Return the current shares outstanding for each outcome."""
        return tuple(self._quantities)

    def cost(self) -> float:
        """Return the current LMSR cost-function value."""
        return self._cost(self._quantities)

    def prices(self) -> tuple[float, ...]:
        """Return the marginal probability for each outcome."""
        scaled = [quantity / self._liquidity for quantity in self._quantities]
        maximum = max(scaled)
        weights = [math.exp(value - maximum) for value in scaled]
        total = sum(weights)
        return tuple(weight / total for weight in weights)

    def trade_cost(self, changes: Iterable[float]) -> float:
        """Return the cost of a trade without changing the market state."""
        validated_changes = self._validate_vector(
            changes, self._outcome_count, "changes"
        )
        new_quantities = [
            quantity + change
            for quantity, change in zip(self._quantities, validated_changes)
        ]
        return self._cost(new_quantities) - self.cost()

    def buy(self, outcome: int, shares: float) -> float:
        """Buy shares in one outcome and return the amount paid."""
        self._validate_outcome(outcome)
        self._validate_shares(shares)
        changes = [0.0] * self._outcome_count
        changes[outcome] = shares
        amount = self.trade_cost(changes)
        self._quantities[outcome] += shares
        return amount

    def sell(self, outcome: int, shares: float) -> float:
        """Sell shares in one outcome and return the amount received."""
        self._validate_outcome(outcome)
        self._validate_shares(shares)
        if shares > self._quantities[outcome]:
            raise ValueError("cannot sell more shares than are outstanding")
        changes = [0.0] * self._outcome_count
        changes[outcome] = -shares
        amount_received = -self.trade_cost(changes)
        self._quantities[outcome] -= shares
        return amount_received

    def _cost(self, quantities: Iterable[float]) -> float:
        scaled = [quantity / self._liquidity for quantity in quantities]
        maximum = max(scaled)
        return self._liquidity * (
            maximum + math.log(sum(math.exp(value - maximum) for value in scaled))
        )

    @staticmethod
    def _validate_vector(
        values: Iterable[float], expected_length: int, name: str
    ) -> list[float]:
        try:
            vector = list(values)
        except TypeError as error:
            raise TypeError(f"{name} must be an iterable of numbers") from error
        if len(vector) != expected_length:
            raise ValueError(f"{name} must contain {expected_length} values")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
               or not math.isfinite(value) for value in vector):
            raise ValueError(f"{name} must contain only finite numbers")
        return [float(value) for value in vector]

    def _validate_outcome(self, outcome: int) -> None:
        if not isinstance(outcome, int) or isinstance(outcome, bool):
            raise TypeError("outcome must be an integer")
        if not 0 <= outcome < self._outcome_count:
            raise IndexError("outcome is outside the market's outcome range")

    @staticmethod
    def _validate_shares(shares: float) -> None:
        if (
            not isinstance(shares, (int, float))
            or isinstance(shares, bool)
            or not math.isfinite(shares)
            or shares <= 0
        ):
            raise ValueError("shares must be a positive finite number")
