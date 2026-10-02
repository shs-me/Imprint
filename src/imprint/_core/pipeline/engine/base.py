import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from imprint._core import constant as c
from imprint._core.configs import MarketDataStream
from imprint._core.footprint.engine import FootprintEngine
from imprint._core.ipc import NodeManager, node_handler
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils.base import TradesArray


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager
    algorithm: FootprintEngine

    __mds: MarketDataStream = field(init=False)

    time_start_analyze: memoryview = field(init=False)
    engine_complete: memoryview = field(init=False)

    agg_trades: TradesArray = field(
        default_factory=lambda: TradesArray(60_000, 4), init=False
    )
    at_max_row: int = field(init=False)
    at_rid: int = field(init=False)
    at_wid: int = field(init=False)

    def __post_init__(self) -> None:
        self.__mds = self.manager.cfgMarketDataStream

        cfgMetrics = self.manager.cfgMetrics
        self.time_start_analyze = cfgMetrics.time_start_reading.view.cast("q")
        self.engine_complete = cfgMetrics.engine_complete.view

        self.at_max_row = self.agg_trades.shape[0]
        self.at_rid, self.at_wid = 0, 0

    @final
    @node_handler()
    def run(self) -> None:
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
        return (wid[0] == rid[0]) and self.algorithm._engine._bbox_is_readed()

    @final
    def __final_actions(self) -> None:
        if self.manager.cfgSetup.backtesting:
            self.algorithm._engine.final_analyze()
            self.algorithm._engine.save_footprint_headers(
                self.algorithm.last_idx[0]
            )

        self.post_final_action()
        self.engine_complete[0] = 1
        self.manager.set_log(
            f"Count prepped ticks: {self.algorithm._engine.counter_ticks} "
            + f"Count signals: {self.algorithm._sync._count_send_signal}"
        )

    @abstractmethod
    def post_final_action(self) -> None: ...

    @abstractmethod
    def alarm_clock(self) -> None: ...

    @abstractmethod
    def set_trade_data(self, raw_data: memoryview) -> None: ...

    @final
    def is_bbox_mode(self, wid: memoryview, rid: memoryview) -> bool:
        return (
            (not self.algorithm.tick_by_tick_analyze) and (wid[0] != rid[0])
        ) and (not (self.algorithm._engine.re_init & c.RIF_session))

    @abstractmethod
    def post_update(self) -> None: ...
