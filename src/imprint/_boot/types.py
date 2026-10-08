from typing import Any, TypedDict

from imprint._core.configs import Percent
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.settings import Timeframe
from imprint._core.utils import (
    AggTradesDecoder,
    ExchangeREST,
    OrderEncoder,
    UserStreamDecoder,
)


class Account(TypedDict):
    leverage: int | list[int]
    balance: float | list[float]
    min_order_size: float | list[float]
    taker_commission: Percent | list[Percent]
    maker_commission: Percent | list[Percent]
    slippage: Percent | list[Percent]
    latency_ms: int | list[int]
    scale_prec: int | list[int]
    active_order_limit: int | list[int]


class Coin(TypedDict):
    symbol: str | list[str]
    tick_size: str | list[str]
    lot_size: str | list[str]


class Backtest(TypedDict):
    account: Account
    coin: Coin
    backtest_start_date: str | list[str]
    backtest_end_date: str | list[str]


class Connector(TypedDict):
    exchange_rest: type[ExchangeREST]
    base_rest_url: str
    agg_trades_decoder: type[AggTradesDecoder[Any]]
    agg_trades_stream_url: str
    user_stream_decoder: type[UserStreamDecoder[Any, Any]]
    user_data_stream_url: str
    order_encoder: type[OrderEncoder[Any]]
    order_stream_url: str


class Live(TypedDict):
    connector: Connector
    leverage: int
    symbol: str


class Footprint(TypedDict):
    timeframe: Timeframe | list[Timeframe]
    chart_range: int | list[int]
    step_tick: int | list[int]
    fp_rows: int | list[int]
    state: bool | list[bool]
    ctrade: bool | list[bool]


class FootprintBatch(TypedDict):
    timeframe: list[Timeframe]
    chart_range: int | list[int]
    step_tick: int | list[int]
    fp_rows: int | list[int]
    state: int | list[int]
    ctrade: int | list[int]


class RiskManagement(TypedDict):
    max_lock_balance: Percent
    max_loss_balance: Percent
    entry_qty: Percent
    tp_dev: Percent
    sl_dev: Percent
    pass_signal_if_analysis_time_big: int
    pass_execute_signal_if_timer_ms_exepired: int


class RiskManagementBatch(TypedDict):
    max_lock_balance: Percent | list[Percent]
    max_loss_balance: Percent | list[Percent]
    entry_qty: Percent | list[Percent]
    tp_dev: Percent | list[Percent]
    sl_dev: Percent | list[Percent]
    pass_signal_if_analysis_time_big: int | list[int]
    pass_execute_signal_if_timer_ms_exepired: int | list[int]


class Strategy(TypedDict):
    algorithm: type[StrategyEngine]
    execution: type[ExecutionEngine]
    footprint: Footprint
    risk_management: RiskManagement


class StrategyBatch(TypedDict):
    algorithm: type[StrategyEngine] | list[type[StrategyEngine]]
    execution: type[ExecutionEngine] | list[type[ExecutionEngine]]
    footprint: Footprint | FootprintBatch
    risk_management: RiskManagement | RiskManagementBatch
