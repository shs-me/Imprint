import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from imprint._core import constant as c
from imprint._core.configs import MarketDataStream
from imprint._core.footprint.engine import StrategyEngine
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
    algorithm: StrategyEngine

    __mds: MarketDataStream = field(init=False)

    time_start_analyze: memoryview = field(init=False)
    engine_complete: memoryview = field(init=False)

    agg_trades: TradesArray = field(
        default_factory=lambda: TradesArray(60_000, 4), init=False
    )
    at_max_row: int = field(init=False)
    at_rid: int = field(init=False)
    at_wid: int = field(init=False)

    @final
    def __post_init__(self) -> None:
        """Initialize core engine metrics, memory views, and index bounds."""
        self.__mds = self.manager.cfgMarketDataStream

        cfgMetrics = self.manager.cfgMetrics
        self.time_start_analyze = cfgMetrics.time_start_reading.view.cast("q")
        self.engine_complete = cfgMetrics.engine_complete.view

        self.at_max_row = self.agg_trades.shape[0]
        self.at_rid, self.at_wid = 0, 0

        self.post_init()

    def post_init(self) -> None: ...

    @final
    @node_handler()
    def run(self) -> None:
        """Run the main processing loop for market data ticks and analysis.

        Polls tasks from the process manager, reads incoming trade data from ring buffers,
        and dispatches updates to the footprint engine.
        """
        _, fp_engine = self.__mds.ring_buf, self.algorithm._engine
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
                    return self.manager.set_proc_sc(
                        scs.COMPLETE, wait_main_task=False
                    )

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

                fp_engine.update_footprint(nPrice, nQty, timestamp, is_sell)

                if self.is_bbox_mode(_.wid_buf, _.rid_buf):
                    continue

                self.time_start_analyze[0] = time.perf_counter_ns()

                fp_engine.analyze_footprint()

                if fp_engine.re_init & c.RIF_session:
                    fp_engine.update_footprint(nPrice, nQty, timestamp, is_sell)
                    if not self.is_bbox_mode(_.wid_buf, _.rid_buf):
                        fp_engine.analyze_footprint()

                self.post_update()

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
        return (
            (wid[0] == rid[0])
            and (self.at_wid == self.at_rid)
            and self.algorithm._engine.bbox_is_read()
        )

    @final
    def __final_actions(self) -> None:
        """Execute final cleanup, metric updates, and logging upon completion."""
        if self.manager.cfgSetup.backtesting:
            self.algorithm._engine.final_analyze()
            self.algorithm._engine.save_footprint_headers(
                self.algorithm._engine.lidx[0]
            )

        self.post_final_action()
        self.engine_complete[0] = 1
        self.manager.set_log(
            f"Count prepped ticks: {self.algorithm._engine.counter_ticks} "
            + f"Count signals: {self.algorithm._sync._count_send_signal}"
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
        return (
            (not self.algorithm.tick_by_tick_analyze) and (wid[0] != rid[0])
        ) and (self.algorithm._engine.is_bbox_mode())

    @abstractmethod
    def post_update(self) -> None:
        """Perform subclass-specific operations after each trade tick update cycle."""
