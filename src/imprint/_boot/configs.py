from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, final

from imprint._core.configs import Percent
from imprint._core.settings import Timeframe
from imprint._core.utils import (
    AggTradesDecoder,
    ExchangeREST,
    OrderEncoder,
    UserStreamDecoder,
)
from imprint.adapters.binance import (
    BinanceAggTradesDecoder,
    BinanceFuturesREST,
    BinanceOrderEncoder,
    BinanceUserStreamDecoder,
)


@final
@dataclass(slots=True)
class Adapters:
    exchange_rest: type[ExchangeREST] = BinanceFuturesREST
    agg_trades_decoder: type[AggTradesDecoder[Any]] = BinanceAggTradesDecoder
    user_stream_decoder: type[UserStreamDecoder[Any, Any]] = (
        BinanceUserStreamDecoder
    )
    order_encoder: type[OrderEncoder[Any]] = BinanceOrderEncoder
    with_execution: bool = True


@final
@dataclass(slots=True)
class AccountBatch:
    leverage: list[int] = field(default_factory=lambda: [20])
    balance: list[float] = field(default_factory=lambda: [100.0])
    min_order_size: list[float] = field(default_factory=lambda: [5.0])
    taker_commission: list[Percent] = field(
        default_factory=lambda: [Percent(0.05)]
    )
    maker_commission: list[Percent] = field(
        default_factory=lambda: [Percent(0.02)]
    )
    slippage: list[Percent] = field(default_factory=lambda: [Percent(0.05)])
    latency_ms: list[int] = field(default_factory=lambda: [100])
    scale_prec: list[int] = field(default_factory=lambda: [8])
    active_order_limit: list[int] = field(default_factory=lambda: [1000])


@final
@dataclass(slots=True)
class FootprintBatch:
    timeframe: list[Timeframe] = field(default_factory=lambda: [Timeframe.H1])
    chart_range: list[int] = field(default_factory=lambda: [1])
    step_tick: list[int] = field(default_factory=lambda: [1])
    state: list[bool] = field(default_factory=lambda: [False])
    ctrade: list[bool] = field(default_factory=lambda: [False])


@final
@dataclass(slots=True)
class RiskManagementBatch:
    max_lock_balance: list[Percent] = field(
        default_factory=lambda: [Percent(10.0)]
    )
    max_loss_balance: list[Percent] = field(
        default_factory=lambda: [Percent(10.0)]
    )
    entry_qty: list[Percent] = field(default_factory=lambda: [Percent(1.0)])
    tp_dev: list[Percent] = field(default_factory=lambda: [Percent(5.0)])
    sl_dev: list[Percent] = field(default_factory=lambda: [Percent(5.0)])
    pass_signal_if_analysis_time_big: list[int] = field(
        default_factory=lambda: [50_000]
    )
    pass_execute_signal_if_timer_ms_exepired: list[int] = field(
        default_factory=lambda: [1000]
    )
