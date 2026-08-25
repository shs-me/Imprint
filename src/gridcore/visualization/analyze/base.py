from dataclasses import dataclass

from numpy import datetime64, float64, int64
from numpy.typing import NDArray

from ..settings import OHLC, CloseTrades, OpenTrades
from . import metrics as m
from .equity_history import analyze_equity_history
from .orders_history import analyze_orders_history


@dataclass
class Stats:
    symbol: str
    start_date: str
    end_date: str
    start_balance: float
    leverage: int
    timeframe: int
    price_mult: int
    qty_mult: int
    scale_mult: int
    equity: NDArray[int64]
    orders: NDArray[int64]
    ohlc: OHLC

    def __post_init__(self) -> None:
        result = analyze_equity_history(self.scale_mult, self.equity)
        self.eq_times: NDArray[datetime64] = result[0]
        self.eq_open: NDArray[float64] = result[1]
        self.eq_high: NDArray[float64] = result[2]
        self.eq_low: NDArray[float64] = result[3]
        self.eq_close: NDArray[float64] = result[4]
        result = analyze_orders_history(
            self.start_balance,
            self.leverage,
            self.price_mult,
            self.qty_mult,
            self.scale_mult,
            self.orders,
        )
        self.trades_close: list[CloseTrades] = result[0]
        self.trades_open: list[OpenTrades] = result[1]
        self.all_pnls: list[float] = result[2]
        self.end_balance: float = result[3] / self.scale_mult
        self.sum_commission: float = result[4]

        result = m.calculate_sharpe_and_sortino_ratio(self.eq_close, self.timeframe)
        self.sharpe_ratio: float = result[0]
        self.sortino_ratio: float = result[1]

        result = m.calculate_dynamic_drawdown(
            self.start_balance, self.eq_high, self.eq_low, self.eq_close
        )
        self.max_dyn_dd_val: float64 = result[0]
        self.max_dyn_dd_pct: float64 = result[1]
        self.dynamic_drawdowns: list[float64] = result[2]

        result = m.calculate_static_drawdown(self.start_balance, self.trades_close)
        self.max_dd_val: float = result[0]
        self.max_dd_pct: float = result[1]
        self.static_drawdowns: list[float] = result[2]

        result = m.calculate_tp_sl_info(self.all_pnls)
        self.sum_tp_count: int = result[0]
        self.sum_tp_pnl: float = result[1]
        self.sum_sl_count: int = result[2]
        self.sum_sl_pnl: float = result[3]

        self.total_trades: int = self.sum_tp_count + self.sum_sl_count
        self.win_rate: float = m.calculate_win_rate(
            self.total_trades, self.sum_tp_count
        )
        self.avg_win: float = m.calculate_avg_win(self.sum_tp_pnl, self.sum_tp_count)
        self.avg_loss: float = m.calculate_avg_loss(self.sum_sl_pnl, self.sum_sl_count)
        self.ev: float = m.calculate_ev(
            self.total_trades,
            self.sum_tp_count,
            self.sum_sl_count,
            self.avg_win,
            self.avg_loss,
        )
        self.net_profit: float = m.calculate_net_profit(
            self.start_balance, self.end_balance
        )
        self.recovery_factor: float = m.calculate_recovery_factor(
            self.max_dyn_dd_val, self.max_dd_val, self.net_profit
        )
        self.profit_factor: float = m.calculate_profit_factor(
            self.sum_tp_pnl, self.sum_sl_pnl, self.sum_commission
        )
        self.avg_hold_time_positions: float = m.calculate_avg_hold_time_positions(
            self.trades_open, self.trades_close
        )
        self.avg_mae_pct: float = m.calculate_avg_mae_pct(self.trades_close)
        self.avg_mfe_pct: float = m.calculate_avg_mfe_pct(self.trades_close)
