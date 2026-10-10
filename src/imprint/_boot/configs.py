"""Configure adapters, account batches, footprint parameters, and risk management presets."""

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
    """Configure protocol adapters and execution behavior for live connectivity.

    Parameters
    ----------
    exchange_rest : type[ExchangeREST], default=BinanceFuturesREST
        REST API client adapter class for exchange interactions.
    agg_trades_decoder : type[AggTradesDecoder[Any]], default=BinanceAggTradesDecoder
        Decoder class for aggregate trade WebSocket/REST feeds.
    user_stream_decoder : type[UserStreamDecoder[Any, Any]], default=BinanceUserStreamDecoder
        Decoder class for user data streams (balance and orders).
    order_encoder : type[OrderEncoder[Any]], default=BinanceOrderEncoder
        Encoder class for translating trade orders to exchange payloads.
    with_execution : bool, default=True
        Whether to enable live order execution functionality.
    """

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
    """Configure batch parameter sequences for account simulation properties.

    Parameters
    ----------
    leverage : list[int], default=[20]
        Sequence of account leverage multipliers.
    balance : list[float], default=[100.0]
        Sequence of initial account cash balances in quote currency.
    min_order_size : list[float], default=[5.0]
        Sequence of minimum allowable order sizes.
    taker_commission : list[Percent], default=[Percent(0.05)]
        Sequence of taker trading fee percentages.
    maker_commission : list[Percent], default=[Percent(0.02)]
        Sequence of maker trading fee percentages.
    slippage : list[Percent], default=[Percent(0.05)]
        Sequence of simulated order execution slippage percentages.
    latency_ms : list[int], default=[100]
        Sequence of simulated order routing latencies in milliseconds.
    scale_prec : list[int], default=[8]
        Sequence of price and quantity scale precisions.
    active_order_limit : list[int], default=[1000]
        Sequence of maximum concurrent active orders allowed.
    """

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
    """Configure batch parameter sequences for footprint chart generation.

    Parameters
    ----------
    timeframe : list[Timeframe], default=[Timeframe.H1]
        Sequence of aggregation timeframes for footprint bars.
    chart_range : list[int], default=[1]
        Sequence of chart depth range parameters.
    step_tick : list[int], default=[1]
        Sequence of price step sizes in ticks per row.
    state : list[bool], default=[False]
        Sequence of boolean flags indicating footprint state logging.
    ctrade : list[bool], default=[False]
        Sequence of boolean flags for cumulative trade tracking.
    """

    timeframe: list[Timeframe] = field(default_factory=lambda: [Timeframe.H1])
    chart_range: list[int] = field(default_factory=lambda: [1])
    step_tick: list[int] = field(default_factory=lambda: [1])
    state: list[bool] = field(default_factory=lambda: [False])
    ctrade: list[bool] = field(default_factory=lambda: [False])


@final
@dataclass(slots=True)
class RiskManagementBatch:
    """Configure batch parameter sequences for risk management and trade limits.

    Parameters
    ----------
    max_lock_balance : list[Percent], default=[Percent(10.0)]
        Sequence of maximum allowable balance lock percentages.
    max_loss_balance : list[Percent], default=[Percent(10.0)]
        Sequence of maximum allowable cumulative drawdown percentages.
    entry_qty : list[Percent], default=[Percent(1.0)]
        Sequence of order sizing percentages relative to account balance.
    tp_dev : list[Percent], default=[Percent(5.0)]
        Sequence of take-profit price deviation percentages.
    sl_dev : list[Percent], default=[Percent(5.0)]
        Sequence of stop-loss price deviation percentages.
    pass_signal_if_analysis_time_big : list[int], default=[50000]
        Sequence of execution thresholds in microseconds; bypasses signal if analysis duration exceeds limit.
    pass_execute_signal_if_timer_ms_exepired : list[int], default=[1000]
        Sequence of timeout thresholds in milliseconds; drops execution signal if timer expires.
    """

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
