"""Multi-timeframe and bar-count aggregation module."""

import numpy as np
from numpy import datetime64, float64, int64
from numpy.typing import NDArray

from imprint._vis.analyze.metrics import calculate_dynamic_drawdown
from imprint._vis.settings import OHLC, ResampledData

BAR_THRESHOLD: int = 144

TIMEFRAME_STEPS: list[tuple[int, str]] = [
    (30 * 1000, "30s"),
    (1 * 60 * 1000, "1m"),
    (5 * 60 * 1000, "5m"),
    (15 * 60 * 1000, "15m"),
    (30 * 60 * 1000, "30m"),
    (1 * 60 * 60 * 1000, "1h"),
    (4 * 60 * 60 * 1000, "4h"),
    (24 * 60 * 60 * 1000, "1d"),
    (7 * 24 * 60 * 60 * 1000, "1w"),
]

NON_TIME_STEPS: list[tuple[int, str]] = [
    (2, "2x"),
    (4, "4x"),
    (8, "8x"),
    (16, "16x"),
    (32, "32x"),
    (64, "64x"),
    (128, "128x"),
]

TIMEFRAME_MAP: dict[int, str] = dict(TIMEFRAME_STEPS)


def _calc_rel_pct(
    values: NDArray[float64], base: float | float64
) -> NDArray[float64]:
    return (
        (values - base) / base * 100.0
        if len(values) > 0
        else np.array([], dtype=float64)
    )


def _reduce_ohlc(
    ohlc: OHLC,
    times: NDArray[datetime64],
    f_idx: NDArray[int64],
    l_idx: NDArray[int64],
) -> OHLC:
    return {
        "open": ohlc["open"][f_idx],
        "high": np.maximum.reduceat(ohlc["high"], f_idx),
        "low": np.minimum.reduceat(ohlc["low"], f_idx),
        "close": ohlc["close"][l_idx],
        "time": times,
    }


def _reduce_equity(
    eq_open: NDArray[float64],
    eq_high: NDArray[float64],
    eq_low: NDArray[float64],
    eq_close: NDArray[float64],
    times: NDArray[datetime64],
    f_idx: NDArray[int64],
    l_idx: NDArray[int64],
    start_balance: float,
) -> tuple[
    NDArray[datetime64],
    NDArray[float64],
    NDArray[float64],
    NDArray[float64],
    NDArray[float64],
    list[float64],
    NDArray[float64],
]:
    r_open = eq_open[f_idx]
    r_close = eq_close[l_idx]
    r_high = np.maximum.reduceat(eq_high, f_idx)
    r_low = np.minimum.reduceat(eq_low, f_idx)
    _, _, dds = calculate_dynamic_drawdown(start_balance, r_high, r_low)
    return (
        times,
        r_open,
        r_high,
        r_low,
        r_close,
        dds,
        _calc_rel_pct(r_close, start_balance),
    )


def build_resampled_timeframes(
    ohlc: OHLC,
    eq_times: NDArray[datetime64],
    eq_open: NDArray[float64],
    eq_high: NDArray[float64],
    eq_low: NDArray[float64],
    eq_close: NDArray[float64],
    start_balance: float,
    base_tf_ms: int,
    dynamic_drawdowns: list[float64],
) -> list[ResampledData]:
    """Generates groupings until bar count fits <= 144 bars."""
    is_time_based: bool = base_tf_ms in TIMEFRAME_MAP
    base_name: str = TIMEFRAME_MAP.get(base_tf_ms, "1x")
    base_p: float64 = (
        ohlc["close"][0] if len(ohlc["close"]) > 0 else float64(1.0)
    )

    resampled_list: list[ResampledData] = [
        {
            "timeframe_ms": base_tf_ms if is_time_based else 1,
            "timeframe_name": base_name,
            "ohlc": ohlc,
            "eq_times": eq_times,
            "eq_open": eq_open,
            "eq_high": eq_high,
            "eq_low": eq_low,
            "eq_close": eq_close,
            "dynamic_drawdowns": dynamic_drawdowns,
            "rel_equity_pct": _calc_rel_pct(eq_close, start_balance),
            "rel_price_pct": _calc_rel_pct(ohlc["close"], base_p),
        }
    ]

    if len(ohlc["time"]) <= BAR_THRESHOLD:
        return resampled_list

    steps = (
        [(ms, name) for ms, name in TIMEFRAME_STEPS if ms > base_tf_ms]
        if is_time_based
        else NON_TIME_STEPS
    )

    for step_val, step_name in steps:
        if is_time_based:
            times_ms = ohlc["time"].astype(int64)
            buckets = (times_ms // step_val) * step_val
            unique_b, f_idx = np.unique(buckets, return_index=True)
            l_idx = np.append(f_idx[1:] - 1, len(times_ms) - 1)
            times = unique_b.astype("datetime64[ms]")
        else:
            n = len(ohlc["time"])
            f_idx = np.arange(0, n, step_val, dtype=int64)
            l_idx = np.minimum(f_idx + step_val - 1, n - 1)
            times = ohlc["time"][f_idx]

        if len(f_idx) == 0:
            break

        g_ohlc = _reduce_ohlc(ohlc, times, f_idx, l_idx)
        eq_t, eq_o, eq_h, eq_l, eq_c, dds, rel_eq = _reduce_equity(
            eq_open,
            eq_high,
            eq_low,
            eq_close,
            times,
            f_idx,
            l_idx,
            start_balance,
        )

        resampled_list.append(
            {
                "timeframe_ms": step_val,
                "timeframe_name": step_name,
                "ohlc": g_ohlc,
                "eq_times": eq_t,
                "eq_open": eq_o,
                "eq_high": eq_h,
                "eq_low": eq_l,
                "eq_close": eq_c,
                "dynamic_drawdowns": dds,
                "rel_equity_pct": rel_eq,
                "rel_price_pct": _calc_rel_pct(g_ohlc["close"], base_p),
            }
        )

        if len(g_ohlc["time"]) <= BAR_THRESHOLD:
            break

    return resampled_list
