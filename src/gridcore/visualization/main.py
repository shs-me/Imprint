import os
from datetime import datetime

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ..core import constant as c
from .analyze import Stats
from .plot import render
from .settings import OHLC


def get_ohlc(price_mult: int, headers: NDArray[int64]) -> OHLC:
    ohlc: OHLC = {
        "open": headers[:, c.BH_Open] / price_mult,
        "high": headers[:, c.BH_High] / price_mult,
        "low": headers[:, c.BH_Low] / price_mult,
        "close": headers[:, c.BH_Close] / price_mult,
        "time": headers[:, c.BH_Time].astype("datetime64[ms]"),
    }
    return ohlc


def get_headers_paths(
    footprint_headers_path: str, symbol: str, start_date: str, end_date: str
) -> list[str]:
    start_datetime: datetime = datetime.fromisoformat(start_date)
    end_datetime: datetime = datetime.fromisoformat(end_date)
    base_headers_path: str = f"{footprint_headers_path}/{symbol}"

    paths: list[str] = [p for p in os.listdir(base_headers_path) if p.endswith(".npy")]
    dates: list[datetime] = sorted(
        [datetime.fromisoformat(p.split("T")[0]) for p in paths]
    )
    needDates: list[datetime] = [
        d for d in dates if (start_datetime <= d <= end_datetime)
    ]
    return [
        f"{base_headers_path}/{datetime.strftime(d, '%Y-%m-%dT%H-%M-%S')}.npy"
        for d in needDates
    ]


def data_load(
    equity_history_path: str, orders_history_path: str, headers_paths: list[str]
) -> tuple[NDArray[int64], NDArray[int64], NDArray[int64]]:
    equity_history: NDArray[int64] = np.load(file=equity_history_path)
    orders_history: NDArray[int64] = np.load(file=orders_history_path)
    headers: NDArray[int64] = np.load(f"{headers_paths.pop(0)}")
    for p in headers_paths:
        _headers: NDArray[np.int64] = np.load(p)
        headers = np.append(headers, _headers, axis=0)

    return equity_history, orders_history, headers


def run(
    footprint_headers_path: str,
    symbol: str,
    start_date: str,
    end_date: str,
    equity_history_path: str,
    orders_history_path: str,
    start_balance: float,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    leverage: int,
    timeframe: int,
) -> None:
    headers_paths = get_headers_paths(
        footprint_headers_path=footprint_headers_path,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    equity_history, orders_history, headers = data_load(
        equity_history_path=equity_history_path,
        orders_history_path=orders_history_path,
        headers_paths=headers_paths,
    )
    ohlc = get_ohlc(
        price_mult=price_mult,
        headers=headers,
    )
    stats = Stats(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        start_balance=start_balance,
        leverage=leverage,
        timeframe=timeframe,
        price_mult=price_mult,
        qty_mult=qty_mult,
        scale_mult=scale_mult,
        equity=equity_history,
        orders=orders_history,
        ohlc=ohlc,
    )
    render(stats)
