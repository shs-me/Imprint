"""Configuration classes and data structures for backtesting and live trading run modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, final

from imprint._core.configs import Connector, Footprint, Percent, RiskManagement
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.settings import Timeframe
from imprint._core.utils import (
    AggTradesDecoder,
    BalanceData,
    ExchangeREST,
    OrderData,
    OrderEncoder,
    UserStreamDecoder,
)

__all__ = [
    "AccountBatch",
    "AggTradesDecoder",
    "Backtest",
    "BalanceData",
    "Connector",
    "ExchangeREST",
    "ExecutionEngine",
    "Footprint",
    "FootprintBatch",
    "Live",
    "OrderData",
    "OrderEncoder",
    "RiskManagement",
    "RiskManagementBatch",
    "Strategy",
    "StrategyBatch",
    "StrategyEngine",
    "UserStreamDecoder",
]


@final
@dataclass(slots=True)
class Live:
    symbol: str
    leverage: int
    connector: Connector
    agg_trades_decoder: type[AggTradesDecoder[Any]]
    user_stream_decoder: type[UserStreamDecoder[Any, Any]]
    order_encoder: type[OrderEncoder[Any]]
    exchange_rest: type[ExchangeREST]


@final
@dataclass(slots=True)
class Backtest:
    account: AccountBatch
    symbols: str | list[str]
    tick_size: str | list[str]
    lot_size: str | list[str]
    backtest_start_date: str | list[str]
    backtest_end_date: str | list[str]


@final
@dataclass(slots=True)
class AccountBatch:
    leverage: int | list[int] = 20
    balance: float | list[float] = 100.0
    min_order_size: float | list[float] = 5.0
    taker_commission: Percent | list[Percent] = field(
        default_factory=lambda: Percent(0.05)
    )
    maker_commission: Percent | list[Percent] = field(
        default_factory=lambda: Percent(0.02)
    )
    slippage: Percent | list[Percent] = field(
        default_factory=lambda: Percent(0.05)
    )
    latency_ms: int | list[int] = 100
    scale_prec: int | list[int] = 8
    active_order_limit: int | list[int] = 1000


@final
@dataclass(slots=True)
class Strategy:
    algorithm: type[StrategyEngine]
    execution: type[ExecutionEngine]
    footprint: Footprint
    risk_management: RiskManagement


@final
@dataclass(slots=True)
class StrategyBatch:
    algorithm: type[StrategyEngine] | list[type[StrategyEngine]]
    execution: type[ExecutionEngine] | list[type[ExecutionEngine]]
    footprint: FootprintBatch
    risk_management: RiskManagementBatch


@final
@dataclass(slots=True)
class FootprintBatch:
    timeframe: Timeframe | list[Timeframe] = Timeframe.H1
    chart_range: int | list[int] = 1
    step_tick: int | list[int] = 1
    state: bool | list[bool] = False
    ctrade: bool | list[bool] = False


@final
@dataclass(slots=True)
class RiskManagementBatch:
    max_lock_balance: Percent | list[Percent] = field(
        default_factory=lambda: Percent(10)
    )
    max_loss_balance: Percent | list[Percent] = field(
        default_factory=lambda: Percent(10)
    )
    entry_qty: Percent | list[Percent] = field(
        default_factory=lambda: Percent(1)
    )
    tp_dev: Percent | list[Percent] = field(default_factory=lambda: Percent(5))
    sl_dev: Percent | list[Percent] = field(default_factory=lambda: Percent(5))
    pass_signal_if_analysis_time_big: int | list[int] = 50_000
    pass_execute_signal_if_timer_ms_exepired: int | list[int] = 1_000
