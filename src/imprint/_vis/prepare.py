import os
from datetime import date, datetime, timedelta

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._vis.settings import OHLC


def get_headers_path(
    symbol: str, timeframe: str, start_date: datetime, end_date: datetime
) -> str | None:
    base_headers_path: str = f"{c.FOOTPRINT_HEADERS_DATA_PATH}/{symbol}"

    paths: list[str] = [
        p.split(".npy")[0]
        for p in os.listdir(base_headers_path)
        if p.endswith(".npy")
    ]
    if paths:
        for p in paths:
            file_timeframe, file_start_time, file_end_time = p.split("_")
            if file_timeframe == timeframe:
                file_start_date: date = date.fromisoformat(file_start_time)
                file_end_date: date = date.fromisoformat(file_end_time)
                if (
                    file_start_date
                    <= start_date.date()
                    <= end_date.date()
                    <= file_end_date
                ):
                    return f"{base_headers_path}/{p}.npy"


def get_need_headers_range(
    start_date: datetime, end_date: datetime, headers: NDArray[int64]
) -> NDArray[int64]:
    start_ts: int = round(start_date.timestamp() * 1000)
    end_ts: int = round((end_date + timedelta(days=1)).timestamp() * 1000)

    times: NDArray[int64] = headers[:, c.BH_Time]

    idx_start: np.intp = np.searchsorted(times, start_ts, side="left")
    idx_end: np.intp = np.searchsorted(times, end_ts, side="right")

    return headers[idx_start:idx_end, :]


def get_ohlc(headers: NDArray[np.int64], price_mult: int) -> OHLC:
    ohlc: OHLC = {
        "open": headers[:, c.BH_Open] / price_mult,
        "high": headers[:, c.BH_High] / price_mult,
        "low": headers[:, c.BH_Low] / price_mult,
        "close": headers[:, c.BH_Close] / price_mult,
        "time": headers[:, c.BH_Time].astype("datetime64[ms]"),
    }
    return ohlc
