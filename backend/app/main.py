from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.markets.LMSR import LMSRMarket
from app.models.Users import Trader


app = FastAPI(title="River Prediction Market API")

markets: dict[str, LMSRMarket] = {
    "demo": LMSRMarket(outcome_count=2, liquidity=10)
}
traders: dict[str, Trader] = {
    "demo": Trader("demo", starting_cash=100)
}


class TraderCreate(BaseModel):
    starting_cash: float = Field(default=0, ge=0)


class TradeRequest(BaseModel):
    trader_id: str
    outcome: int = Field(ge=0)
    shares: float = Field(gt=0)


def get_market(market_id: str) -> LMSRMarket:
    market = markets.get(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return market


def get_trader(trader_id: str) -> Trader:
    trader = traders.get(trader_id)
    if trader is None:
        raise HTTPException(status_code=404, detail="Trader not found")
    return trader


def market_response(market_id: str, market: LMSRMarket) -> dict[str, Any]:
    return {
        "market_id": market_id,
        "outcome_count": market.outcome_count,
        "prices": market.prices(),
        "quantities": market.quantities,
    }


def trader_response(
    trader_id: str, trader: Trader, market_id: str, market: LMSRMarket
) -> dict[str, Any]:
    positions = trader.positions.get(market, {})
    return {
        "trader_id": trader_id,
        "cash": trader.cash,
        "market_id": market_id,
        "positions": positions,
        "total_value": trader.total_value(market),
    }


@app.get("/markets/{market_id}")
def read_market(market_id: str) -> dict[str, Any]:
    market = get_market(market_id)
    return market_response(market_id, market)


@app.post("/traders/{trader_id}", status_code=201)
def create_trader(trader_id: str, request: TraderCreate) -> dict[str, Any]:
    if trader_id in traders:
        raise HTTPException(status_code=409, detail="Trader already exists")
    traders[trader_id] = Trader(trader_id, request.starting_cash)
    return {
        "trader_id": trader_id,
        "cash": traders[trader_id].cash,
    }


@app.get("/traders/{trader_id}")
def read_trader(
    trader_id: str, market_id: str = "demo"
) -> dict[str, Any]:
    trader = get_trader(trader_id)
    market = get_market(market_id)
    return trader_response(trader_id, trader, market_id, market)


@app.post("/markets/{market_id}/buy")
def buy_shares(
    market_id: str, request: TradeRequest
) -> dict[str, Any]:
    market = get_market(market_id)
    trader = get_trader(request.trader_id)
    try:
        paid = trader.buy(market, request.outcome, request.shares)
    except (IndexError, TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "action": "buy",
        "cost": paid,
        **market_response(market_id, market),
        **trader_response(request.trader_id, trader, market_id, market),
    }


@app.post("/markets/{market_id}/sell")
def sell_shares(
    market_id: str, request: TradeRequest
) -> dict[str, Any]:
    market = get_market(market_id)
    trader = get_trader(request.trader_id)
    try:
        revenue = trader.sell(market, request.outcome, request.shares)
    except (IndexError, TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "action": "sell",
        "revenue": revenue,
        **market_response(market_id, market),
        **trader_response(request.trader_id, trader, market_id, market),
    }