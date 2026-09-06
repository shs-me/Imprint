from datetime import datetime
from typing import TypedDict

from numpy import datetime64, float64
from numpy.typing import NDArray


class OHLC(TypedDict):
    open: NDArray[float64]
    high: NDArray[float64]
    low: NDArray[float64]
    close: NDArray[float64]
    time: NDArray[datetime64]


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
