from datetime import datetime
from typing import TypedDict

from numpy import datetime64, float64
from numpy.typing import NDArray


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


class OHLC(TypedDict):
    open: NDArray[float64]
    high: NDArray[float64]
    low: NDArray[float64]
    close: NDArray[float64]
    time: NDArray[datetime64]


class ResampledData(TypedDict):
    timeframe_ms: int
    timeframe_name: str
    ohlc: OHLC
    eq_times: NDArray[datetime64]
    eq_open: NDArray[float64]
    eq_high: NDArray[float64]
    eq_low: NDArray[float64]
    eq_close: NDArray[float64]
    dynamic_drawdowns: list[float64]
    rel_equity_pct: NDArray[float64]
    rel_price_pct: NDArray[float64]
