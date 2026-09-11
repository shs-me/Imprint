from dataclasses import dataclass
from typing import Any, final

from imprint._core.configs import (
    Account,
    Connector,
    Footprint,
    RiskManagement,
)
from imprint._core.footprint import FootprintEngine
from imprint._core.pipeline.executing import BaseExecution
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
    "BaseExecution",
    "Connector",
    "ExchangeREST",
    "Footprint",
    "FootprintEngine",
    "Live",
    "OrderData",
    "OrderEncoder",
    "RiskManagement",
    "Strategy",
    "UserStreamDecoder",
]


@final
@dataclass(slots=True)
class Backtest:
    account: Account
    tick_size: str = "0.01"
    lot_size: str = "0.001"
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"


@final
@dataclass(slots=True)
class Live:
    connector: Connector
    agg_trades_decoder: type[AggTradesDecoder[Any]]
    user_stream_decoder: type[UserStreamDecoder[Any]]
    order_encoder: type[OrderEncoder]
    exchange_rest: type[ExchangeREST]


@final
@dataclass(slots=True)
class Strategy:
    algorithm: type[FootprintEngine]
    footprint: Footprint
    risk_management: RiskManagement
