"""Multi-timeframe bar and equity aggregation module."""

from typing import TypedDict

import numpy as np
from numpy import datetime64, float64, int64
from numpy.typing import NDArray

from imprint.visualization.analyze.metrics import calculate_dynamic_drawdown
from imprint.visualization.settings import OHLC

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


def resample_ohlc(ohlc: OHLC, target_tf_ms: int) -> OHLC:
    """Aggregates OHLC arrays into target timeframe buckets."""
    if len(ohlc["time"]) == 0:
        return {
            "open": np.array([], dtype=float64),
            "high": np.array([], dtype=float64),
            "low": np.array([], dtype=float64),
            "close": np.array([], dtype=float64),
            "time": np.array([], dtype="datetime64[ms]"),
        }

    times_ms: NDArray[int64] = ohlc["time"].astype(int64)
    bucket_keys: NDArray[int64] = (times_ms // target_tf_ms) * target_tf_ms
    unique_buckets, first_indices = np.unique(bucket_keys, return_index=True)
    last_indices: NDArray[int64] = np.append(
        first_indices[1:] - 1, len(times_ms) - 1
    )

    opens: NDArray[float64] = ohlc["open"][first_indices]
    closes: NDArray[float64] = ohlc["close"][last_indices]
    highs: NDArray[float64] = np.maximum.reduceat(ohlc["high"], first_indices)
    lows: NDArray[float64] = np.minimum.reduceat(ohlc["low"], first_indices)
    times: NDArray[datetime64] = unique_buckets.astype("datetime64[ms]")

    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "time": times,
    }


def resample_equity_data(
    eq_times: NDArray[datetime64],
    eq_open: NDArray[float64],
    eq_high: NDArray[float64],
    eq_low: NDArray[float64],
    eq_close: NDArray[float64],
    start_balance: float,
    target_tf_ms: int,
) -> tuple[
    NDArray[datetime64],
    NDArray[float64],
    NDArray[float64],
    NDArray[float64],
    NDArray[float64],
    list[float64],
    NDArray[float64],
]:
    """Aggregates equity bars and recalculates dynamic drawdown and returns."""
    if len(eq_times) == 0:
        return (
            np.array([], dtype="datetime64[ms]"),
            np.array([], dtype=float64),
            np.array([], dtype=float64),
            np.array([], dtype=float64),
            np.array([], dtype=float64),
            [],
            np.array([], dtype=float64),
        )

    times_ms: NDArray[int64] = eq_times.astype(int64)
    bucket_keys: NDArray[int64] = (times_ms // target_tf_ms) * target_tf_ms
    unique_buckets, first_indices = np.unique(bucket_keys, return_index=True)
    last_indices: NDArray[int64] = np.append(
        first_indices[1:] - 1, len(times_ms) - 1
    )

    res_open: NDArray[float64] = eq_open[first_indices]
    res_close: NDArray[float64] = eq_close[last_indices]
    res_high: NDArray[float64] = np.maximum.reduceat(eq_high, first_indices)
    res_low: NDArray[float64] = np.minimum.reduceat(eq_low, first_indices)
    res_times: NDArray[datetime64] = unique_buckets.astype("datetime64[ms]")

    _, _, dds = calculate_dynamic_drawdown(start_balance, res_high, res_low)
    rel_pct: NDArray[float64] = (
        (res_close - start_balance) / start_balance * 100.0
    )

    return res_times, res_open, res_high, res_low, res_close, dds, rel_pct


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
    """Builds resampled timeframe hierarchy based on the > 144 bar rule."""
    base_name: str = "Base"
    for ms, name in TIMEFRAME_STEPS:
        if ms == base_tf_ms:
            base_name = name
            break

    base_p: float64 = (
        ohlc["close"][0] if len(ohlc["close"]) > 0 else float64(1.0)
    )
    rel_price_base: NDArray[float64] = (
        ((ohlc["close"] - base_p) / base_p * 100.0)
        if len(ohlc["close"]) > 0
        else np.array([], dtype=float64)
    )
    rel_eq_base: NDArray[float64] = (
        ((eq_close - start_balance) / start_balance * 100.0)
        if len(eq_close) > 0
        else np.array([], dtype=float64)
    )

    resampled_list: list[ResampledData] = [
        {
            "timeframe_ms": base_tf_ms,
            "timeframe_name": base_name,
            "ohlc": ohlc,
            "eq_times": eq_times,
            "eq_open": eq_open,
            "eq_high": eq_high,
            "eq_low": eq_low,
            "eq_close": eq_close,
            "dynamic_drawdowns": dynamic_drawdowns,
            "rel_equity_pct": rel_eq_base,
            "rel_price_pct": rel_price_base,
        }
    ]

    current_bars: int = len(ohlc["time"])
    if current_bars <= BAR_THRESHOLD:
        return resampled_list

    start_idx: int = 0
    for idx, (ms, _) in enumerate(TIMEFRAME_STEPS):
        if ms > base_tf_ms:
            start_idx = idx
            break
    else:
        return resampled_list

    for step_idx in range(start_idx, len(TIMEFRAME_STEPS)):
        step_ms, step_name = TIMEFRAME_STEPS[step_idx]
        grouped_ohlc: OHLC = resample_ohlc(ohlc, step_ms)
        bar_count: int = len(grouped_ohlc["time"])
        if bar_count == 0:
            break

        eq_t, eq_o, eq_h, eq_l, eq_c, dds, rel_eq = resample_equity_data(
            eq_times=eq_times,
            eq_open=eq_open,
            eq_high=eq_high,
            eq_low=eq_low,
            eq_close=eq_close,
            start_balance=start_balance,
            target_tf_ms=step_ms,
        )

        rel_p: NDArray[float64] = (
            (grouped_ohlc["close"] - base_p) / base_p * 100.0
        )

        resampled_list.append(
            {
                "timeframe_ms": step_ms,
                "timeframe_name": step_name,
                "ohlc": grouped_ohlc,
                "eq_times": eq_t,
                "eq_open": eq_o,
                "eq_high": eq_h,
                "eq_low": eq_l,
                "eq_close": eq_c,
                "dynamic_drawdowns": dds,
                "rel_equity_pct": rel_eq,
                "rel_price_pct": rel_p,
            }
        )

        if bar_count <= BAR_THRESHOLD:
            break

    return resampled_list
