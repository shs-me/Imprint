import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from numpy import int64

import imprint._core.constant as c
from imprint._core.footprint.models import Footprint
from imprint._core.ipc import NodeManager
from imprint._core.types import SetLogMethodSignature, StrategyProtocol


@dataclass(slots=True)
class SyncWithExecution(ABC):
    """Coordinates signal emission and synchronization with execution nodes."""

    manager: NodeManager

    trade_time: memoryview = field(init=False)
    _signal_id: int = field(default=0, init=False)
    _count_send_signal: int = field(default=0, init=False)

    def reset(self) -> None:
        self._signal_id, self._count_send_signal = 0, 0

    @final
    @property
    def base_tp_dev(self) -> int:
        return self.manager.cfgRiskManagement.tp_dev.fixed

    @final
    @property
    def base_sl_dev(self) -> int:
        return self.manager.cfgRiskManagement.sl_dev.fixed

    @final
    @property
    def safe_lag(self) -> int:
        return self.manager.cfgRiskManagement.pass_signal_time

    @final
    @property
    def signal_id(self) -> int:
        """Increment and return the next monotonically increasing signal sequence identifier."""
        self._signal_id += 1
        return self._signal_id

    @final
    def send_signal(
        self,
        nPrice: int | int64,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        pass_lag: bool,
        tp_dev: int = 0,
        sl_dev: int = 0,
    ) -> None | int:
        """Construct and publish a trade execution signal to the signal ring buffer.

        Validates consumer and publisher latency constraints before serializing order
        parameters into the shared signal stream.

        Returns
        -------
        int | None
            Assigned signal identifier if published successfully, or None if dropped
            due to safe lag threshold violations.
        """
        _ = self.manager.mlSignalStream
        # - - -
        if not pass_lag and (not self.lag_is_safe()):
            return

        if _.ring_buf.lag_not_is_safe():
            return

        order_param = 0
        order_param |= c.OF_LONG if is_long else c.OF_SHORT
        order_param |= c.OF_BUY if is_buy else c.OF_SELL
        order_param |= c.OF_MARKET if is_market else c.OF_LIMIT
        order_param |= c.OF_NEW

        _.set_data(
            signal_id=self.signal_id,
            nPrice=int(nPrice),
            timestamp=timestamp,
            order_param=order_param,
            tp_dev=tp_dev if tp_dev else self.base_tp_dev,
            sl_dev=sl_dev if sl_dev else self.base_sl_dev,
        )
        self.sync_with_execution()
        self._count_send_signal += 1
        return self._signal_id

    @abstractmethod
    def sync_with_execution(self) -> None:
        """Synchronize signal stream state with the downstream execution node."""

    @final
    def lag_is_safe(self) -> bool:
        """Check whether current analysis elapsed latency is within the safe limit.

        Computes the delta between current wall-clock performance counter and
        the initial cycle read time recorded in shared memory."""
        lag: int = round(time.time() * 1000) - self.trade_time[0]
        return lag < self.safe_lag


@dataclass(slots=True)
class StrategyEngine(StrategyProtocol, ABC):
    """Abstract base algorithm router driving footprint processing and signal routing.

    Subclasses implement analytical hooks for order book cluster adjustments,
    bar completions, and intra-bar updates.

    Attributes
    ----------
    is_backtest : bool
        Flag indicating if the engine is running in backtesting mode.
    tick_by_tick_analyze : bool
        Flag indicating whether intra-bar cluster or bar updates are active.
    atr_period : int
        Period length for Average True Range smoothing calculations.
    park_period : int
        Period length for Parkinson volatility calculations.
    ma_volume_period : int
        Period length for moving average volume calculations.
    ma_count_trade_period : int
        Period length for moving average trade count calculations.
    ma_avg_trade_size_period : int
        Period length for moving average average trade size calculations.
    big_cluster_mult : float
        Multiplier threshold for detecting anomalous volume clusters.
    fp : Footprint
        Footprint data model instance containing market microstructure matrices.
    """

    _sync: SyncWithExecution
    is_backtest: bool

    tick_by_tick_analyze: bool = field(default=True, init=False)
    atr_period: int = field(default=14, init=False)
    park_period: int = field(default=12, init=False)
    ma_volume_period: int = field(default=21, init=False)
    ma_count_trade_period: int = field(default=21, init=False)
    ma_avg_trade_size_period: int = field(default=21, init=False)
    big_cluster_mult: float = field(default=0.33, init=False)

    fp: Footprint = field(init=False)
    logger: SetLogMethodSignature = field(init=False)

    @final
    def __post_init__(self) -> None:
        if self.on_bar_update.__module__ != __name__:
            self.tick_by_tick_analyze = True
        else:
            self.tick_by_tick_analyze = False

        self.logger = self._sync.manager.set_log
        self.post_init()

    def post_init(self) -> None:
        """Perform secondary algorithmic state initialization after core setup."""

    @override
    def on_bar_update(
        self, idYmin: int, idYmax: int, idx: int, lidx: int
    ) -> None:
        """Handle real-time updates within the active bar timeframe.

        Parameters
        ----------
        idYmin : int
            Minimum price index bounding the active update region.
        idYmax : int
            Maximum price index bounding the active update region.
        idx : int
            Current bar index.
        lidx : int
            Last processed bar index.
        """

    @override
    def on_bar_close(self, idx: int, lidx: int) -> None:
        """Handle completion and closure of the current time bar."""

    @final
    def send_signal(
        self,
        is_market: bool,
        is_long: bool,
        is_buy: bool,
        nPrice: int | int64,
        /,
        idx: int | None = None,
        tp_dev: int = 0,
        sl_dev: int = 0,
        pass_lag: bool = True,
    ) -> int | None:
        """Convert price grid coordinates into normalized price and route a trading signal.

        Derives bar timestamps based on execution mode (historical trade timestamp
        in backtest or current epoch time in live mode) before relaying to synchronization.

        Parameters
        ----------
        is_market : bool
            Execution order type flag. If True, market order; if False, limit order.
        is_long : bool
            Target position direction flag. If True, position is long; if False, short.
        is_buy : bool
            Order trade side flag. If True, order side is buy; if False, sell.
        idy : int64
            Price-axis index in the footprint matrix to convert into normalized price.
        idx : int | None, default=None
            Bar index used to look up historical bar timestamp in backtest mode.
            If None, defaults to the active bar index in ``last_idx[0]``.
        tp_dev : int, default=0
            Take-profit price deviation in steps. If 0, uses system default.
        sl_dev : int, default=0
            Stop-loss price deviation in steps. If 0, uses system default.
        pass_lag : bool, default=True
            Flag to bypass publisher analysis lag checks.

        Returns
        -------
        int | None
            Assigned signal identifier if successfully sent, or None if aborted
            by lag constraints.
        """
        idx = idx if (idx is not None) else self.fp.last_idx[0]
        timestamp = round(
            self.fp[idx].ind.last_trade_time
            if self.is_backtest
            else time.time() * 1000
        )
        return self._sync.send_signal(
            nPrice=nPrice,
            timestamp=timestamp,
            is_long=is_long,
            is_buy=is_buy,
            is_market=is_market,
            tp_dev=tp_dev,
            sl_dev=sl_dev,
            pass_lag=pass_lag,
        )

    @override
    def reset(self) -> None:
        self._sync.reset()
