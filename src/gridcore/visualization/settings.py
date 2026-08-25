from datetime import datetime
from typing import TypedDict


class CloseTrades(TypedDict):
    time: datetime
    color: str
    is_long: bool
    balance: float
    price: float
    pnl: float
    pnl_pct: float
    mae: float
    mae_pct: float
    mfe: float
    mfe_pct: float


class OpenTrades(TypedDict):
    time: datetime
    balance: float
    price: float
    is_long: bool
    is_buy: bool
