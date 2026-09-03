from dataclasses import dataclass, field

from numpy import datetime64, float64, int64
from numpy.typing import NDArray

from ..settings import OHLC, CloseTrades, OpenTrades
from .equity_history import analyze_equity_history
from .metrics import (
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
from .orders_history import analyze_orders_history


@dataclass(slots=True)
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

    eq_times: NDArray[datetime64] = field(init=False)
    eq_open: NDArray[float64] = field(init=False)
    eq_high: NDArray[float64] = field(init=False)
    eq_low: NDArray[float64] = field(init=False)
    eq_close: NDArray[float64] = field(init=False)
    trades_close: list[CloseTrades] = field(init=False)
    trades_open: list[OpenTrades] = field(init=False)
    all_pnls: list[float] = field(init=False)
    end_balance: float = field(init=False)
    sum_commission: float = field(init=False)
    sharpe_ratio: float = field(init=False)
    sortino_ratio: float = field(init=False)
    max_dyn_dd_val: float64 = field(init=False)
    max_dyn_dd_pct: float64 = field(init=False)
    dynamic_drawdowns: list[float64] = field(init=False)
    max_dd_val: float = field(init=False)
    max_dd_pct: float = field(init=False)
    static_drawdowns: list[float] = field(init=False)
    sum_tp_count: int = field(init=False)
    sum_tp_pnl: float = field(init=False)
    sum_sl_count: int = field(init=False)
    sum_sl_pnl: float = field(init=False)
    total_trades: int = field(init=False)
    win_rate: float = field(init=False)
    avg_win: float = field(init=False)
    avg_loss: float = field(init=False)
    ev: float = field(init=False)
    net_profit: float = field(init=False)
    recovery_factor: float = field(init=False)
    profit_factor: float = field(init=False)
    avg_hold_time_positions: float = field(init=False)
    avg_mae_pct: float = field(init=False)
    avg_mfe_pct: float = field(init=False)

    def __post_init__(self) -> None:
        result = analyze_equity_history(self.scale_mult, self.equity)
        self.eq_times = result[0]
        self.eq_open = result[1]
        self.eq_high = result[2]
        self.eq_low = result[3]
        self.eq_close = result[4]
        result = analyze_orders_history(
            self.start_balance,
            self.leverage,
            self.price_mult,
            self.qty_mult,
            self.scale_mult,
            self.orders,
        )
        self.trades_close = result[0]
        self.trades_open = result[1]
        self.all_pnls = result[2]
        self.end_balance = result[3] / self.scale_mult
        self.sum_commission = result[4]

        result = calculate_sharpe_and_sortino_ratio(self.eq_close, self.timeframe)
        self.sharpe_ratio = result[0]
        self.sortino_ratio = result[1]

        result = calculate_dynamic_drawdown(
            self.start_balance, self.eq_high, self.eq_low
        )
        self.max_dyn_dd_val = result[0]
        self.max_dyn_dd_pct = result[1]
        self.dynamic_drawdowns = result[2]

        result = calculate_static_drawdown(self.start_balance, self.trades_close)
        self.max_dd_val = result[0]
        self.max_dd_pct = result[1]
        self.static_drawdowns = result[2]

        result = calculate_tp_sl_info(self.all_pnls)
        self.sum_tp_count = result[0]
        self.sum_tp_pnl = result[1]
        self.sum_sl_count = result[2]
        self.sum_sl_pnl = result[3]

        self.total_trades = self.sum_tp_count + self.sum_sl_count
        self.win_rate = calculate_win_rate(self.total_trades, self.sum_tp_count)
        self.avg_win = calculate_avg_win(self.sum_tp_pnl, self.sum_tp_count)
        self.avg_loss = calculate_avg_loss(self.sum_sl_pnl, self.sum_sl_count)
        self.ev = calculate_ev(
            self.total_trades,
            self.sum_tp_count,
            self.sum_sl_count,
            self.avg_win,
            self.avg_loss,
        )
        self.net_profit = calculate_net_profit(self.start_balance, self.end_balance)
        self.recovery_factor = calculate_recovery_factor(
            self.max_dyn_dd_val, self.max_dd_val, self.net_profit
        )
        self.profit_factor = calculate_profit_factor(
            self.sum_tp_pnl, self.sum_sl_pnl, self.sum_commission
        )
        self.avg_hold_time_positions = calculate_avg_hold_time_positions(
            self.trades_open, self.trades_close
        )
        self.avg_mae_pct = calculate_avg_mae_pct(self.trades_close)
        self.avg_mfe_pct = calculate_avg_mfe_pct(self.trades_close)
