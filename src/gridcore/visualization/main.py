import os
from datetime import datetime

import numpy as np
import pandas as pd
from numpy import int64
from numpy.typing import NDArray

from ..core import constant as c
from .analyze import Stats
from .plot import render


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


def get_ohlc(price_mult: int, headers: NDArray[int64]) -> pd.DataFrame:
    df = pd.DataFrame()
    df["Open"] = headers[:, c.BH_Open] / price_mult
    df["High"] = headers[:, c.BH_High] / price_mult
    df["Low"] = headers[:, c.BH_Low] / price_mult
    df["Close"] = headers[:, c.BH_Close] / price_mult
    df["OpenTime"] = headers[:, c.BH_Time]

    df.set_index(df["OpenTime"], inplace=True)

    df.index = pd.to_datetime(df.index, unit="ms")
    return df


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
        footprint_headers_path, symbol, start_date, end_date
    )
    equity_history, orders_history, headers = data_load(
        equity_history_path, orders_history_path, headers_paths
    )
    ohlc = get_ohlc(price_mult, headers)
    stats = Stats(
        symbol,
        start_date,
        end_date,
        start_balance,
        leverage,
        timeframe,
        price_mult,
        qty_mult,
        scale_mult,
        equity_history,
        orders_history,
        ohlc,
    )
    render(stats)
