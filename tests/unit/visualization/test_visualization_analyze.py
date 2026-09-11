"""Unit tests for `imprint.visualization.analyze`.

Covers 100% of the analytical layer:
- `metrics.py`: financial metrics, ratios, drawdowns, and edge-cases.
- `equity_history.py`: array scaling and timestamp conversion.
- `orders_history.py`: position reconstruction, PnL, MAE/MFE, commissions.
- `base.py`: end-to-end `Stats` aggregation.
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from imprint._core import constant as c
from imprint._vis.analyze.base import Stats
from imprint._vis.analyze.equity_history import analyze_equity_history
from imprint._vis.analyze.metrics import (
    calculate_avg_hold_time_positions,
    calculate_avg_loss,
    calculate_avg_mae_pct,
    calculate_avg_mfe_pct,
    calculate_avg_win,
    calculate_dynamic_drawdown,
    calculate_ev,
    calculate_net_profit,
    calculate_profit_factor,
    calculate_recovery_factor,
    calculate_sharpe_and_sortino_ratio,
    calculate_static_drawdown,
    calculate_tp_sl_info,
    calculate_win_rate,
)
from imprint._vis.analyze.orders_history import analyze_orders_history
from imprint._vis.settings import OHLC, CloseTrades, OpenTrades


class TestMetrics:
    def test_calculate_net_profit(self) -> None:
        assert calculate_net_profit(1000.0, 1500.0) == 500.0
        assert calculate_net_profit(1000.0, 800.0) == -200.0
        assert calculate_net_profit(1000.0, 1000.0) == 0.0

    def test_calculate_recovery_factor(self) -> None:
        # Uses max_dyn_dd_val when > 0
        assert (
            calculate_recovery_factor(
                max_dyn_dd_val=200.0, max_dd_val=100.0, net_profit=400.0
            )
            == 2.0
        )
        # Falls back to max_dd_val when max_dyn_dd_val <= 0
        assert (
            calculate_recovery_factor(
                max_dyn_dd_val=0.0, max_dd_val=100.0, net_profit=250.0
            )
            == 2.5
        )
        # Returns 0.0 when both drawdowns are zero
        assert (
            calculate_recovery_factor(
                max_dyn_dd_val=0.0, max_dd_val=0.0, net_profit=500.0
            )
            == 0.0
        )

    def test_calculate_tp_sl_info(self) -> None:
        all_pnls = [100.0, -50.0, 200.0, -30.0, 0.0]
        # pnl > 0 -> TP, else -> SL
        sum_tp_count, sum_tp_pnl, sum_sl_count, sum_sl_pnl = (
            calculate_tp_sl_info(all_pnls)
        )
        assert sum_tp_count == 2
        assert sum_tp_pnl == 300.0
        assert sum_sl_count == 3  # -50, -30, and 0.0
        assert sum_sl_pnl == -80.0

    def test_calculate_win_rate(self) -> None:
        assert calculate_win_rate(total_trades=10, sum_tp_count=6) == 60.0
        assert calculate_win_rate(total_trades=0, sum_tp_count=0) == 0.0

    def test_calculate_avg_win(self) -> None:
        assert calculate_avg_win(sum_tp_pnl=300.0, sum_tp_count=3) == 100.0
        assert calculate_avg_win(sum_tp_pnl=0.0, sum_tp_count=0) == 0.0

    def test_calculate_avg_loss(self) -> None:
        assert calculate_avg_loss(sum_sl_pnl=-150.0, sum_sl_count=3) == -50.0
        assert calculate_avg_loss(sum_sl_pnl=0.0, sum_sl_count=0) == 0.0

    def test_calculate_ev(self) -> None:
        # 10 trades: 6 wins (avg 100), 4 losses (avg -50) -> (0.6 * 100) - (0.4 * 50) = 40.0
        ev = calculate_ev(
            total_trades=10,
            sum_tp_count=6,
            sum_sl_count=4,
            avg_win=100.0,
            avg_loss=-50.0,
        )
        assert ev == pytest.approx(40.0)
        # Empty trades
        assert calculate_ev(0, 0, 0, 0.0, 0.0) == 0.0

    def test_calculate_profit_factor(self) -> None:
        # Normal case: gross_profit / gross_loss
        # gross_loss = abs(-100 + -(50)) = 150.0
        pf = calculate_profit_factor(
            sum_tp_pnl=300.0, sum_sl_pnl=-100.0, sum_commission=50.0
        )
        assert pf == pytest.approx(300.0 / 150.0)

        # Zero loss with positive profit
        assert (
            calculate_profit_factor(
                sum_tp_pnl=200.0, sum_sl_pnl=0.0, sum_commission=0.0
            )
            == 200.0
        )

        # Zero loss with zero or negative profit -> defaults to 1.0
        assert (
            calculate_profit_factor(
                sum_tp_pnl=0.0, sum_sl_pnl=0.0, sum_commission=0.0
            )
            == 1.0
        )

    def test_calculate_avg_mfe_pct(self) -> None:
        trades: list[CloseTrades] = [  # pyright: ignore[reportAssignmentType]
            {"mfe_pct": 1.5},
            {"mfe_pct": 2.5},
            {"mfe_pct": 0.0},
        ]
        assert calculate_avg_mfe_pct(trades) == pytest.approx(2.0)
        assert calculate_avg_mfe_pct([]) == 0.0
        assert calculate_avg_mfe_pct([{"mfe_pct": 0.0}]) == 0.0  # pyright: ignore[reportArgumentType]

    def test_calculate_avg_mae_pct(self) -> None:
        trades: list[CloseTrades] = [  # pyright: ignore[reportAssignmentType]
            {"mae_pct": -1.0},
            {"mae_pct": -3.0},
            {"mae_pct": 0.0},
        ]
        assert calculate_avg_mae_pct(trades) == pytest.approx(-2.0)
        assert calculate_avg_mae_pct([]) == 0.0
        assert calculate_avg_mae_pct([{"mae_pct": 0.0}]) == 0.0  # pyright: ignore[reportArgumentType]

    def test_calculate_avg_hold_time_positions(self) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 10, 30, 0, tzinfo=UTC)  # 30 mins
        t2 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        t3 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)  # 60 mins

        trades_open: list[OpenTrades] = [{"time": t0}, {"time": t2}]  # pyright: ignore[reportAssignmentType]
        trades_close: list[CloseTrades] = [{"time": t1}, {"time": t3}]  # pyright: ignore[reportAssignmentType]

        assert (
            calculate_avg_hold_time_positions(trades_open, trades_close) == 45.0
        )
        assert calculate_avg_hold_time_positions([], []) == 0.0

    def test_calculate_sharpe_and_sortino_ratio(self) -> None:
        # Empty or single-element equity
        assert calculate_sharpe_and_sortino_ratio(np.array([]), 300_000) == (
            0.0,
            0.0,
        )
        assert calculate_sharpe_and_sortino_ratio(
            np.array([100.0]), 300_000
        ) == (0.0, 0.0)

        # Constant equity (zero std)
        flat_eq = np.array([100.0, 100.0, 100.0], dtype=np.float64)
        assert calculate_sharpe_and_sortino_ratio(flat_eq, 300_000) == (
            0.0,
            0.0,
        )

        # Normal series with mixed returns (both positive and negative)
        mixed_eq = np.array(
            [100.0, 102.0, 101.0, 103.0, 102.5, 105.0], dtype=np.float64
        )
        sharpe, sortino = calculate_sharpe_and_sortino_ratio(mixed_eq, 300_000)
        assert sharpe > 0
        assert sortino > 0

        # Series with only strictly positive returns (no downside returns)
        positive_eq = np.array([100.0, 102.0, 104.0, 106.0], dtype=np.float64)
        pos_sharpe, pos_sortino = calculate_sharpe_and_sortino_ratio(
            positive_eq, 300_000
        )
        assert pos_sharpe == pos_sortino > 0

    def test_calculate_static_drawdown(self) -> None:
        start_balance = 1000.0
        trades: list[CloseTrades] = [  # pyright: ignore[reportAssignmentType]
            {"balance": 1100.0},  # peak = 1100
            {"balance": 990.0},  # dd_val = 110, dd_pct = 10%
            {"balance": 880.0},  # dd_val = 220, dd_pct = 20%
            {"balance": 1200.0},  # new peak = 1200
        ]
        max_dd_val, max_dd_pct, static_dds = calculate_static_drawdown(
            start_balance, trades
        )
        assert max_dd_val == 220.0
        assert max_dd_pct == pytest.approx(20.0)
        assert static_dds == [0.0, -10.0, -20.0, 0.0]

    def test_calculate_dynamic_drawdown(self) -> None:
        start_balance = 100.0
        eq_high = np.array([110.0, 105.0, 120.0], dtype=np.float64)
        eq_low = np.array([99.0, 88.0, 115.0], dtype=np.float64)

        max_dyn_dd_val, max_dyn_dd_pct, dds = calculate_dynamic_drawdown(
            start_balance, eq_high, eq_low
        )
        # Point 0: peak=110, low=99 -> dd=11, dd_pct = 10%
        # Point 1: peak=110, low=88 -> dd=22, dd_pct = 20%
        # Point 2: peak=120, low=115 -> dd=5, dd_pct = 4.16%
        assert max_dyn_dd_val == 22.0
        assert max_dyn_dd_pct == pytest.approx(20.0)
        assert dds[0] == pytest.approx(-10.0)
        assert dds[1] == pytest.approx(-20.0)


class TestEquityHistory:
    def test_analyze_equity_history(self) -> None:
        scale_mult = 10**8
        equity = np.zeros((2, c.EH_ConstantCount), dtype=np.int64)
        equity[0, c.EH_Timestamp] = 1_700_000_000_000
        equity[0, c.EH_Open] = 100 * scale_mult
        equity[0, c.EH_High] = 110 * scale_mult
        equity[0, c.EH_Low] = 90 * scale_mult
        equity[0, c.EH_Close] = 105 * scale_mult

        equity[1, c.EH_Timestamp] = 1_700_000_300_000
        equity[1, c.EH_Open] = 105 * scale_mult
        equity[1, c.EH_High] = 115 * scale_mult
        equity[1, c.EH_Low] = 100 * scale_mult
        equity[1, c.EH_Close] = 112 * scale_mult

        eq_times, eq_open, eq_high, eq_low, eq_close = analyze_equity_history(
            scale_mult, equity
        )

        assert eq_times.dtype == "datetime64[ms]"
        assert eq_times[0] == np.datetime64("2023-11-14T22:13:20.000")
        assert eq_open[0] == 100.0
        assert eq_high[0] == 110.0
        assert eq_low[0] == 90.0
        assert eq_close[0] == 105.0

        assert eq_open[1] == 105.0
        assert eq_high[1] == 115.0
        assert eq_low[1] == 100.0
        assert eq_close[1] == 112.0


class TestOrdersHistory:
    def test_analyze_orders_history_long_and_short_cycles(self) -> None:
        price_mult = 100
        qty_mult = 1_000
        scale_mult = 10**8
        leverage = 10
        start_balance = 1_000.0

        # We will create 5 orders:
        # Row 0: Open Long (Buy, Filled)
        # Row 1: Close Long at Profit (Sell, Filled, PnL > 0)
        # Row 2: Unfilled order (Canceled, should be ignored)
        # Row 3: Open Short (Sell, Filled)
        # Row 4: Close Short at Loss (Buy, Filled, PnL < 0)
        orders = np.zeros((5, c.TP_ConstantCount), dtype=np.int64)

        # 0: Open Long
        orders[0, c.TP_timestamp] = 1_700_000_000_000
        orders[0, c.TP_nPrice] = 100 * price_mult
        orders[0, c.TP_nQty] = 2 * qty_mult
        orders[0, c.TP_order_param] = (
            c.OF_FILLED | c.OF_LONG | c.OF_BUY | c.OF_LIMIT
        )
        orders[0, c.TP_nCommission] = round(0.05 * scale_mult)

        # 1: Close Long (Profit)
        orders[1, c.TP_timestamp] = 1_700_000_060_000
        orders[1, c.TP_nPrice] = 110 * price_mult  # price rose -> profit
        orders[1, c.TP_nQty] = 2 * qty_mult
        orders[1, c.TP_order_param] = c.OF_FILLED | c.OF_LONG | c.OF_SELL
        orders[1, c.TP_nCommission] = round(0.05 * scale_mult)
        orders[1, c.TP_nMAE] = round(-5.0 * scale_mult)
        orders[1, c.TP_nMFE] = 0

        # 2: Unfilled order
        orders[2, c.TP_timestamp] = 1_700_000_100_000
        orders[2, c.TP_order_param] = c.OF_CANCELED

        # 3: Open Short
        orders[3, c.TP_timestamp] = 1_700_000_120_000
        orders[3, c.TP_nPrice] = 100 * price_mult
        orders[3, c.TP_nQty] = 1 * qty_mult
        orders[3, c.TP_order_param] = c.OF_FILLED | c.OF_SHORT | c.OF_SELL
        orders[3, c.TP_nCommission] = round(0.02 * scale_mult)

        # 4: Close Short (Loss)
        orders[4, c.TP_timestamp] = 1_700_000_180_000
        orders[4, c.TP_nPrice] = (
            105 * price_mult
        )  # price rose -> loss for short
        orders[4, c.TP_nQty] = 1 * qty_mult
        orders[4, c.TP_order_param] = c.OF_FILLED | c.OF_SHORT | c.OF_BUY
        orders[4, c.TP_nCommission] = round(0.02 * scale_mult)
        orders[4, c.TP_nMAE] = 0
        orders[4, c.TP_nMFE] = round(2.0 * scale_mult)

        trades_close, trades_open, all_pnls, _end_nbalance, sum_commission = (
            analyze_orders_history(
                start_balance=start_balance,
                leverage=leverage,
                price_mult=price_mult,
                qty_mult=qty_mult,
                scale_mult=scale_mult,
                orders=orders,
            )
        )

        assert len(trades_open) == 2
        assert len(trades_close) == 2
        assert len(all_pnls) == 2
        assert sum_commission == pytest.approx(0.14)

        # Long Open verification
        assert trades_open[0]["is_long"] is True
        assert trades_open[0]["is_buy"] is True
        assert trades_open[0]["price"] == 100.0

        # Long Close verification (Win)
        tc_long = trades_close[0]
        assert tc_long["color"] == "green"
        assert tc_long["is_long"] is True
        assert tc_long["price"] == 110.0
        assert tc_long["pnl"] == pytest.approx(20.0)
        assert tc_long["pnl_pct"] == pytest.approx(10.0)
        assert tc_long["mae"] == -5.0
        assert tc_long["mae_pct"] < 0
        assert tc_long["mfe"] == 0.0
        assert tc_long["mfe_pct"] == 0.0

        # Short Open verification
        assert trades_open[1]["is_long"] is False
        assert trades_open[1]["is_buy"] is False
        assert trades_open[1]["price"] == 100.0

        # Short Close verification (Loss)
        tc_short = trades_close[1]
        assert tc_short["color"] == "red"
        assert tc_short["is_long"] is False
        assert tc_short["price"] == 105.0
        assert tc_short["pnl"] == pytest.approx(-5.0)
        assert tc_short["pnl_pct"] == pytest.approx(-5.0)
        assert tc_short["mfe"] == 2.0
        assert tc_short["mfe_pct"] > 0
        assert tc_short["mae"] == 0.0
        assert tc_short["mae_pct"] == 0.0


class TestStats:
    def test_stats_dataclass_initialization(self) -> None:
        scale_mult = 10**8
        price_mult = 100
        qty_mult = 1_000
        start_balance = 1_000.0

        # Sample OHLC
        ohlc: OHLC = {
            "open": np.array([100.0, 102.0], dtype=np.float64),
            "high": np.array([105.0, 106.0], dtype=np.float64),
            "low": np.array([98.0, 101.0], dtype=np.float64),
            "close": np.array([102.0, 104.0], dtype=np.float64),
            "time": np.array(
                ["2026-01-01T00:00", "2026-01-01T00:05"], dtype="datetime64[ms]"
            ),
        }

        # Sample Equity
        equity = np.zeros((2, c.EH_ConstantCount), dtype=np.int64)
        equity[0, c.EH_Timestamp] = 1_767_225_600_000
        equity[0, c.EH_Open] = 1000 * scale_mult
        equity[0, c.EH_High] = 1020 * scale_mult
        equity[0, c.EH_Low] = 990 * scale_mult
        equity[0, c.EH_Close] = 1010 * scale_mult

        equity[1, c.EH_Timestamp] = 1_767_225_900_000
        equity[1, c.EH_Open] = 1010 * scale_mult
        equity[1, c.EH_High] = 1030 * scale_mult
        equity[1, c.EH_Low] = 1005 * scale_mult
        equity[1, c.EH_Close] = 1025 * scale_mult

        # Sample Orders (1 Open Long, 1 Close Long)
        orders = np.zeros((2, c.TP_ConstantCount), dtype=np.int64)
        orders[0, c.TP_timestamp] = 1_767_225_600_000
        orders[0, c.TP_nPrice] = 100 * price_mult
        orders[0, c.TP_nQty] = 1 * qty_mult
        orders[0, c.TP_order_param] = c.OF_FILLED | c.OF_LONG | c.OF_BUY

        orders[1, c.TP_timestamp] = 1_767_225_900_000
        orders[1, c.TP_nPrice] = 105 * price_mult
        orders[1, c.TP_nQty] = 1 * qty_mult
        orders[1, c.TP_order_param] = c.OF_FILLED | c.OF_LONG | c.OF_SELL
        orders[1, c.TP_nMAE] = round(-1.0 * scale_mult)

        stats = Stats(
            symbol="BTCUSDT",
            start_date="2026-01-01",
            end_date="2026-01-02",
            start_balance=start_balance,
            leverage=10,
            timeframe=300_000,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            equity=equity,
            orders=orders,
            ohlc=ohlc,
        )

        assert stats.symbol == "BTCUSDT"
        assert stats.total_trades == 1
        assert stats.win_rate == 100.0
        assert stats.sum_tp_count == 1
        assert stats.sum_sl_count == 0
        assert stats.avg_win == pytest.approx(5.0)
        assert stats.avg_loss == 0.0
        assert stats.net_profit == pytest.approx(5.0)
        assert stats.end_balance == pytest.approx(1005.0)
        assert len(stats.eq_close) == 2
        assert len(stats.trades_close) == 1
        assert len(stats.trades_open) == 1
        assert stats.avg_mae_pct < 0
        assert stats.avg_mfe_pct == 0.0
