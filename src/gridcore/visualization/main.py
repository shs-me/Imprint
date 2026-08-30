import os
from datetime import date, datetime

import numpy as np
from loguru import logger
from numpy import int64
from numpy.typing import NDArray

from ..core import constant as c
from ..core.settings import Timeframe
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


def get_headers_path(
    footprint_headers_path: str,
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str,
) -> str | None:
    start_datetime: date = datetime.fromisoformat(start_date)
    end_datetime: date = datetime.fromisoformat(end_date)
    base_headers_path: str = f"{footprint_headers_path}/{symbol}"

    paths: list[str] = [
        p.split(".npy")[0] for p in os.listdir(base_headers_path) if p.endswith(".npy")
    ]
    if paths:
        for p in paths:
            file_timeframe, file_start_time, file_end_time = p.split("_")
            if file_timeframe == timeframe:
                file_start_date: datetime = datetime.fromisoformat(
                    file_start_time.split("T")[0]
                )
                file_end_date: datetime = datetime.fromisoformat(
                    file_end_time.split("T")[0]
                )
                if file_start_date <= start_datetime <= end_datetime <= file_end_date:
                    return f"{base_headers_path}/{p}.npy"


def data_load(
    equity_history_path: str, orders_history_path: str, headers_path: str
) -> tuple[NDArray[int64], NDArray[int64], NDArray[int64]]:
    equity_history: NDArray[int64] = np.load(file=equity_history_path)
    orders_history: NDArray[int64] = np.load(file=orders_history_path)
    headers: NDArray[int64] = np.load(headers_path)
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
    timeframe: Timeframe,
) -> None:
    headers_path = get_headers_path(
        footprint_headers_path=footprint_headers_path,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe.name,
    )
    if headers_path is None:
        return logger.warning(
            (
                f"Not found headers with timeframe {timeframe.name}"
                f"start date {start_date}, end date {end_date}"
            )
        )

    equity_history, orders_history, headers = data_load(
        equity_history_path=equity_history_path,
        orders_history_path=orders_history_path,
        headers_path=headers_path,
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
