"""Configuration classes and data structures for backtesting and live trading run modes."""

from dataclasses import dataclass
from typing import Any, final

from imprint._core.configs import (
    Account,
    Connector,
    Footprint,
    RiskManagement,
)
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.utils import (
    AggTradesDecoder,
    BalanceData,
    ExchangeREST,
    OrderData,
    OrderEncoder,
    UserStreamDecoder,
)

__all__ = [
    "Account",
    "AggTradesDecoder",
    "Backtest",
    "BalanceData",
    "Connector",
    "ExchangeREST",
    "ExecutionEngine",
    "Footprint",
    "Live",
    "OrderData",
    "OrderEncoder",
    "RiskManagement",
    "Strategy",
    "StrategyEngine",
    "UserStreamDecoder",
]


@final
@dataclass(slots=True)
class Backtest:
    """Configure parameters and metadata for historical backtesting runs.

    Parameters
    ----------
    account : Account
        Trading account configuration including starting balance, leverage, and risk parameters.
    tick_size : str, default="0.01"
        Minimum price movement increment (tick size) as a string representation.
    lot_size : str, default="0.001"
        Minimum base asset order quantity increment (lot size) as a string representation.
    backtest_start_date : str, default="2026-01-01"
        Backtest simulation start timestamp in ``"YYYY-MM-DD"`` format.
    backtest_end_date : str, default="2026-01-01"
        Backtest simulation end timestamp in ``"YYYY-MM-DD"`` format.

    Attributes
    ----------
    account : Account
        Trading account configuration.
    tick_size : str
        Minimum price movement increment.
    lot_size : str
        Minimum base asset order quantity increment.
    backtest_start_date : str
        Simulation start timestamp.
    backtest_end_date : str
        Simulation end timestamp.
    """

    account: Account
    tick_size: str = "0.01"
    lot_size: str = "0.001"
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"


@final
@dataclass(slots=True)
class Live:
    """Configure exchange connectivity, decoders, encoders, and leverage for live trading sessions.

    Parameters
    ----------
    leverage : int
        Target account trading leverage multiplier. Must be strictly positive.
    connector : Connector
        Exchange WebSocket and REST connector configuration.
    agg_trades_decoder : type[AggTradesDecoder[Any]]
        Decoder class for parsing incoming aggregated trade websocket messages.
    user_stream_decoder : type[UserStreamDecoder[Any, Any]]
        Decoder class for parsing user account and order execution streams.
    order_encoder : type[OrderEncoder[Any]]
        Encoder class for serializing and signing outgoing order payloads.
    exchange_rest : type[ExchangeREST]
        REST API adapter class for querying account balances, rules, and placing REST requests.

    Attributes
    ----------
    leverage : int
        Target account leverage multiplier.
    connector : Connector
        Exchange connector configuration.
    agg_trades_decoder : type[AggTradesDecoder[Any]]
        Aggregated trades decoder class.
    user_stream_decoder : type[UserStreamDecoder[Any, Any]]
        User data stream decoder class.
    order_encoder : type[OrderEncoder[Any]]
        Order encoder class.
    exchange_rest : type[ExchangeREST]
        Exchange REST client adapter class.
    """

    leverage: int
    connector: Connector
    agg_trades_decoder: type[AggTradesDecoder[Any]]
    user_stream_decoder: type[UserStreamDecoder[Any, Any]]
    order_encoder: type[OrderEncoder[Any]]
    exchange_rest: type[ExchangeREST]


@final
@dataclass(slots=True)
class Strategy:
    """Configure the core algorithm, footprint chart settings, and risk management parameters.

    Parameters
    ----------
    algorithm : type[StrategyEngine]
        Trading strategy algorithm class derived from ``StrategyEngine``.
    footprint : Footprint
        Footprint chart configuration (timeframe, delta profiles, volume bins).
    risk_management : RiskManagement
        Risk management rules (stop loss, take profit, position sizing limits).

    Attributes
    ----------
    algorithm : type[StrategyEngine]
        Trading strategy algorithm class.
    footprint : Footprint
        Footprint chart configuration.
    risk_management : RiskManagement
        Risk management rules.
    """

    algorithm: type[StrategyEngine]
    footprint: Footprint
    risk_management: RiskManagement
