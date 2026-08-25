from datetime import datetime

import numpy as np
from numpy import float64
from numpy.typing import NDArray

from ..settings import CloseTrades, OpenTrades


def calculate_net_profit(start_balance: float, end_balance: float) -> float:
    return end_balance - start_balance


def calculate_recovery_factor(
    max_dyn_dd_val: float, max_dd_val: float, net_profit: float
) -> float:
    denom_dd: float = max_dyn_dd_val if (max_dyn_dd_val > 0) else max_dd_val
    return (net_profit / denom_dd) if (denom_dd > 0) else 0.0


def calculate_tp_sl_info(all_pnls: list[float]) -> tuple[int, float, int, float]:
    sum_tp_count: int = 0
    sum_tp_pnl: float = 0.0
    sum_sl_count: int = 0
    sum_sl_pnl: float = 0.0
    for pnl in all_pnls:
        if pnl > 0:
            sum_tp_pnl += pnl
            sum_tp_count += 1
        else:
            sum_sl_pnl += pnl
            sum_sl_count += 1

    return sum_tp_count, sum_tp_pnl, sum_sl_count, sum_sl_pnl


def calculate_win_rate(total_trades: int, sum_tp_count: int) -> float:
    return (sum_tp_count / total_trades * 100) if total_trades > 0 else 0.0


def calculate_avg_win(sum_tp_pnl: float, sum_tp_count: int) -> float:
    return (sum_tp_pnl / sum_tp_count) if (sum_tp_count > 0) else 0.0


def calculate_avg_loss(sum_sl_pnl: float, sum_sl_count: int) -> float:
    return (sum_sl_pnl / sum_sl_count) if (sum_sl_count > 0) else 0.0


def calculate_ev(
    total_trades: int,
    sum_tp_count: int,
    sum_sl_count: int,
    avg_win: float,
    avg_loss: float,
) -> float:
    return (
        ((sum_tp_count / total_trades) * avg_win)
        - ((sum_sl_count / total_trades) * abs(avg_loss))
        if total_trades > 0
        else 0.0
    )


def calculate_profit_factor(
    sum_tp_pnl: float, sum_sl_pnl: float, sum_commission: float
) -> float:
    gross_profit: float = sum_tp_pnl
    gross_loss: float = abs(sum_sl_pnl + -(sum_commission))
    return (
        gross_profit / gross_loss
        if gross_loss > 0
        else (gross_profit if gross_profit > 0 else 1.0)
    )


def calculate_avg_mfe_pct(trades_close: list[CloseTrades]) -> float:
    mfe_pcts: list[float] = [
        tc["mfe_pct"] for tc in trades_close if (tc["mfe_pct"] > 0)
    ]
    return float(np.mean(mfe_pcts) if mfe_pcts else 0.0)


def calculate_avg_mae_pct(trades_close: list[CloseTrades]) -> float:
    mae_pcts: list[float] = [
        tc["mae_pct"] for tc in trades_close if (tc["mae_pct"] < 0)
    ]
    return float(np.mean(mae_pcts) if mae_pcts else 0.0)


def calculate_avg_hold_time_positions(
    trades_open: list[OpenTrades], trades_close: list[CloseTrades]
) -> float:
    hold_times: list[float] = []
    for i in range(min(len(trades_open), len(trades_close))):
        t_o: datetime = trades_open[i]["time"]
        t_c: datetime = trades_close[i]["time"]
        duration: float = (t_c - t_o).total_seconds() / 60.0
        hold_times.append(duration)

    return float(np.mean(hold_times) if hold_times else 0.0)


def calculate_sharpe_and_sortino_ratio(
    eq_close: NDArray[float64], timeframe: int
) -> tuple[float, float]:
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    if len(eq_close) > 1:
        returns: NDArray[float64] = np.diff(eq_close) / eq_close[:-1]
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

        if len(returns) > 0 and np.std(returns) > 0:
            periods_per_year = (365 * 24 * 60 * 60 * 1000) / timeframe
            ann_factor = np.sqrt(periods_per_year)

            mean_ret = np.mean(returns)
            std_ret = np.std(returns, ddof=1)

            sharpe_ratio = (mean_ret / std_ret) * ann_factor

            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0:
                downside_std = np.sqrt(np.mean(downside_returns**2))
                sortino_ratio = (
                    (mean_ret / downside_std) * ann_factor if downside_std > 0 else 0.0
                )
            else:
                sortino_ratio = sharpe_ratio

    return sharpe_ratio, sortino_ratio


def calculate_static_drawdown(
    start_balance: float, trades_close: list[CloseTrades]
) -> tuple[float, float, list[float]]:
    balances: list[float] = [start_balance] + [tc["balance"] for tc in trades_close]

    peak: float = start_balance
    max_dd_val: float = 0.0
    max_dd_pct: float = 0.0
    static_drawdowns: list[float] = []

    for b in balances[1:]:
        if b > peak:
            peak = b

        dd_val: float = peak - b
        dd_pct: float = (dd_val / peak) * 100.0 if peak > 0 else 0.0

        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_val = dd_val

        static_drawdowns.append(-dd_pct)

    return max_dd_val, max_dd_pct, static_drawdowns


def calculate_dynamic_drawdown(
    start_balance: float,
    eq_high: NDArray[float64],
    eq_low: NDArray[float64],
    eq_close: NDArray[float64],
) -> tuple[float64, float64, list[float64]]:
    peak: float64 = float64(start_balance)
    max_dyn_dd_val: float64 = float64(0.0)
    max_dyn_dd_pct: float64 = float64(0.0)
    dynamic_drawdowns: list[float64] = []

    for high, low, c_val in zip(eq_high, eq_low, eq_close):
        if high > peak:
            peak = high

        dd_val: float64 = peak - low
        dd_pct: float64 = (dd_val / peak) * 100.0 if (peak > 0) else float64(0.0)

        if dd_pct > max_dyn_dd_pct:
            max_dyn_dd_pct = dd_pct
            max_dyn_dd_val = dd_val

        dynamic_drawdowns.append(-dd_pct)

    return max_dyn_dd_val, max_dyn_dd_pct, dynamic_drawdowns
