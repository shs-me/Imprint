import importlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from imprint._core import constant as c
from imprint._core.footprint.engine import StrategyEngine
from imprint._core.footprint.engine.reader import FootprintEngine
from imprint._core.footprint.engine.strategy import SyncWithExecution
from imprint._core.ipc import NodeManager, node_handler
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils.base import TradesArray


@dataclass(slots=True)
class Base(ABC):
    """Abstract base engine for processing market data ticks and executing strategies.

    Parameters
    ----------
    manager : NodeManager
        Inter-process communication and configuration manager for the engine node.
    algorithm : StrategyEngine
        Active strategy container holding the footprint engine and synchronization state.

    Attributes
    ----------
    manager : NodeManager
        Inter-process communication and configuration manager for the engine node.
    algorithm : StrategyEngine
        Active strategy container holding the footprint engine and synchronization state.
    time_start_analyze : memoryview
        Shared memory view storing the timestamp when analysis starts, cast as 64-bit integer (`q`).
    engine_complete : memoryview
        Shared memory view indicating engine completion status flag.
    agg_trades : TradesArray
        Contiguous buffer array storing aggregated trades data.
    at_max_row : int
        Maximum capacity (row count) of the aggregated trades buffer.
    at_rid : int
        Current read index within the aggregated trades buffer.
    at_wid : int
        Current write index within the aggregated trades buffer.
    """

    manager: NodeManager
    sync: SyncWithExecution

    engine: FootprintEngine = field(init=False)
    strategy: StrategyEngine = field(init=False)
    time_start_analyze: memoryview = field(init=False)
    engine_complete: memoryview = field(init=False)

    agg_trades: TradesArray = field(
        default_factory=lambda: TradesArray(60_000, 4), init=False
    )
    at_max_row: int = field(init=False)
    at_rid: int = field(default=0, init=False)
    at_wid: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        cfgMetrics = self.manager.cfgMetrics
        self.time_start_analyze = cfgMetrics.time_start_reading.view.cast("q")
        self.engine_complete = cfgMetrics.engine_complete.view

        self.at_max_row = self.agg_trades.shape[0]
        self.init()
        self.engine = FootprintEngine(
            manager=self.manager, strategy=self.strategy
        )
        self.strategy.fp = self.engine.fp

    def init(self) -> None:
        cfgSetup = self.manager.cfgSetup
        c_name: str = cfgSetup.algorithm_class_name
        if not hasattr(self, "strategy") or (
            self.strategy.__class__.__name__ != c_name
        ):
            m_name: str = cfgSetup.algorithm_module
            strategy_type: type[StrategyEngine] = getattr(
                importlib.import_module(m_name), c_name
            )
            self.strategy = strategy_type(
                _sync=self.sync, is_backtest=cfgSetup.backtesting
            )
            self.manager.set_log(
                f"{self.strategy.__class__.__name__} used as {StrategyEngine.__name__}"
            )

    @final
    @node_handler()
    def run(self) -> None:
        """Run the main processing loop for market data ticks and analysis.

        Polls tasks from the process manager, reads incoming trade data from ring buffers,
        and dispatches updates to the footprint engine.
        """
        _ = self.manager.cfgMarketDataStream.ring_buf
        # - - -
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(
                        scs.EXIT, wait_main_task=False
                    )

                if task & scs.COMPLETE and self.__complete(
                    _.wid_buf, _.rid_buf
                ):
                    self.__final_actions()
                    self.manager.complete()
                    continue

                if task & scs.RESET:
                    self.reset()

            if _.wid_buf[0] == _.rid_buf[0]:
                self.alarm_clock()

            if _.wid_buf[0] != _.rid_buf[0]:
                self.set_trade_data(_.get_data())

            while self.at_rid != self.at_wid:
                nPrice, nQty, timestamp, is_sell = self.agg_trades[
                    self.at_rid, :
                ]
                new_rid = self.at_rid + 1
                self.at_rid = new_rid if new_rid < self.at_max_row else 0

                self.engine.update_footprint(nPrice, nQty, timestamp, is_sell)

                if self.is_bbox_mode(_.wid_buf, _.rid_buf):
                    continue

                self.time_start_analyze[0] = time.perf_counter_ns()

                self.engine.analyze_footprint()

                if self.engine.re_init & c.RIF_session:
                    self.engine.update_footprint(
                        nPrice, nQty, timestamp, is_sell
                    )
                    if not self.is_bbox_mode(_.wid_buf, _.rid_buf):
                        self.engine.analyze_footprint()

                self.post_update()

    def reset(self) -> None:
        self.init()
        self.at_rid, self.at_wid = 0, 0
        self.engine.strategy = self.strategy
        self.strategy.fp = self.engine.fp
        self.engine.reset()

    @final
    def __complete(self, wid: memoryview, rid: memoryview) -> bool:
        """Verify whether all buffered market data and trades have been fully processed.

        Parameters
        ----------
        wid : memoryview
            Write index buffer for the market data stream.
        rid : memoryview
            Read index buffer for the market data stream.

        Returns
        -------
        bool
            True if buffers are caught up, trade queues are empty, and bounding box is read.
        """
        return (wid[0] == rid[0]) and (self.at_wid == self.at_rid)

    @final
    def __final_actions(self) -> None:
        """Execute final cleanup, metric updates, and logging upon completion."""
        self.engine.final_analyze()
        self.engine.save_footprint_headers(self.engine.lidx[0])
        self.post_final_action()
        self.engine_complete[0] = 1
        self.manager.set_log(
            f"Count prepped ticks: {self.engine.counter_ticks} "
            + f"Count signals: {self.strategy._sync._count_send_signal}"
        )

    @abstractmethod
    def post_final_action(self) -> None:
        """Execute subclass-specific actions upon engine completion."""

    @abstractmethod
    def alarm_clock(self) -> None:
        """Handle idling or waiting behavior when input buffers are empty."""

    @abstractmethod
    def set_trade_data(self, raw_data: memoryview) -> None:
        """Decode and write raw trade data into the internal trade buffers.

        Parameters
        ----------
        raw_data : memoryview
            Raw binary trade payload from the data stream ring buffer.
        """

    @final
    def is_bbox_mode(self, wid: memoryview, rid: memoryview) -> bool:
        """Determine whether the engine is operating in bounding box (non-tick-by-tick) mode.

        Parameters
        ----------
        wid : memoryview
            Write index buffer for the market data stream.
        rid : memoryview
            Read index buffer for the market data stream.

        Returns
        -------
        bool
            True if analysis is in bounding box mode and session re-initialization is inactive.
        """
        return (wid[0] != rid[0]) and self.engine.is_bbox_mode()

    @abstractmethod
    def post_update(self) -> None:
        """Perform subclass-specific operations after each trade tick update cycle."""
