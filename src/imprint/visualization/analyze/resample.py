"""Multi-timeframe bar and equity aggregation module."""

import numpy as np
from numpy import datetime64, float64, int64
from numpy.typing import NDArray

from imprint.visualization.analyze.metrics import calculate_dynamic_drawdown
from imprint.visualization.settings import OHLC, ResampledData

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

TIMEFRAME_MAP: dict[int, str] = dict(TIMEFRAME_STEPS)


def _get_resample_indices(
    times: NDArray[datetime64], target_tf_ms: int
) -> tuple[NDArray[datetime64], NDArray[int64], NDArray[int64]]:
    """Helper to calculate unique time buckets and boundary indices."""
    times_ms: NDArray[int64] = times.astype(int64)
    bucket_keys: NDArray[int64] = (times_ms // target_tf_ms) * target_tf_ms
    unique_buckets, first_indices = np.unique(bucket_keys, return_index=True)
    last_indices: NDArray[int64] = np.append(
        first_indices[1:] - 1, len(times_ms) - 1
    )
    return unique_buckets.astype("datetime64[ms]"), first_indices, last_indices


def _calc_rel_pct(
    values: NDArray[float64], base: float | float64
) -> NDArray[float64]:
    """Helper to calculate percentage change relative to a base value."""
    if len(values) == 0:
        return np.array([], dtype=float64)
    return (values - base) / base * 100.0


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

    times, first_indices, last_indices = _get_resample_indices(
        ohlc["time"], target_tf_ms
    )

    return {
        "open": ohlc["open"][first_indices],
        "high": np.maximum.reduceat(ohlc["high"], first_indices),
        "low": np.minimum.reduceat(ohlc["low"], first_indices),
        "close": ohlc["close"][last_indices],
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

    res_times, first_indices, last_indices = _get_resample_indices(
        eq_times, target_tf_ms
    )

    res_open: NDArray[float64] = eq_open[first_indices]
    res_close: NDArray[float64] = eq_close[last_indices]
    res_high: NDArray[float64] = np.maximum.reduceat(eq_high, first_indices)
    res_low: NDArray[float64] = np.minimum.reduceat(eq_low, first_indices)

    _, _, dds = calculate_dynamic_drawdown(start_balance, res_high, res_low)
    rel_pct: NDArray[float64] = _calc_rel_pct(res_close, start_balance)

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
    base_name: str = TIMEFRAME_MAP.get(base_tf_ms, "Base")

    base_p: float64 = (
        ohlc["close"][0] if len(ohlc["close"]) > 0 else float64(1.0)
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
            "rel_equity_pct": _calc_rel_pct(eq_close, start_balance),
            "rel_price_pct": _calc_rel_pct(ohlc["close"], base_p),
        }
    ]

    if len(ohlc["time"]) <= BAR_THRESHOLD:
        return resampled_list

    for step_ms, step_name in TIMEFRAME_STEPS:
        if step_ms <= base_tf_ms:
            continue

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
                "rel_price_pct": _calc_rel_pct(grouped_ohlc["close"], base_p),
            }
        )

        if bar_count <= BAR_THRESHOLD:
            break

    return resampled_list
