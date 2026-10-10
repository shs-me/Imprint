"""Imprint algorithmic trading, footprint charting, and market microstructure framework.

Imprint provides a high-performance IPC-driven architecture for quantitative
strategy execution and footprint chart aggregation across historical backtesting
and live exchange connections.

Core Entry Points
-----------------
backtest : BacktestBuilder
    Fluent builder for configuring multi-symbol historical backtesting sessions,
    downloading market trade histories, and running Streamlit visualizer dashboards.
live : LiveBuilder
    Fluent builder for initializing live trading sessions, connecting WebSocket feeds,
    and routing live order executions.

Base Strategy & Execution Engines
---------------------------------
StrategyEngine
    Abstract router driving footprint order flow calculations, volume cluster analysis,
    and execution signal generation.
ExecutionEngine
    Abstract router managing order lifecycles, position state, and signal handling.

Protocol & Exchange Adapters
----------------------------
ExchangeREST
    Base REST API client for exchange account state and instrument specification queries.
AggTradesDecoder
    Decoder for aggregate trade WebSocket/REST feeds.
UserStreamDecoder
    Decoder for private user data streams (account balances and order fills).
OrderEncoder
    Encoder for formatting outgoing order transmission payloads.

Utilities & Type Aliases
------------------------
pct : Percent
    Scaled percentage datatype helper.
tf : Timeframe
    Supported bar aggregation timeframes (e.g. M1, H1).
constant
    System-wide path, bitmask, and bit-flag constant definitions.
"""

import imprint._boot.logger  # noqa: F401 # pyright: ignore[reportUnusedImport]
from imprint._boot.backtest import BacktestBuilder as _BBuilder
from imprint._boot.live import LiveBuilder as _LBuilder
from imprint._core import constant
from imprint._core.configs import Percent as pct
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.settings import Timeframe as tf
from imprint._core.utils import (
    AggTradesDecoder,
    BalanceData,
    ExchangeREST,
    OrderData,
    OrderEncoder,
    UserStreamDecoder,
)

__all__ = [
    "AggTradesDecoder",
    "BalanceData",
    "ExchangeREST",
    "ExecutionEngine",
    "OrderData",
    "OrderEncoder",
    "StrategyEngine",
    "UserStreamDecoder",
    "backtest",
    "constant",
    "live",
    "pct",
    "tf",
]

backtest = _BBuilder
live = _LBuilder
