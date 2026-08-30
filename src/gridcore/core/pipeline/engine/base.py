import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ...footprint.engine import FootprintEngine
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler


@dataclass
class Base(ABC):
    manager: NodeManager
    engine: FootprintEngine

    ds_cell_amount: int = field(init=False)
    ds_data_size: int = field(init=False)
    ds_data: memoryview = field(init=False)
    ds_data_header: memoryview = field(init=False)
    ds_wid: memoryview = field(init=False)
    ds_rid: memoryview = field(init=False)

    time_start_analyze: memoryview = field(init=False)
    engine_complete: memoryview = field(init=False)

    agg_trades: NDArray[int64] = field(init=False)
    at_max_row: int = field(init=False)
    at_rid: int = field(init=False)
    at_wid: int = field(init=False)

    def __post_init__(self) -> None:
        cfgDS = self.manager.cfgDataStream
        self.ds_cell_amount = cfgDS.cell_amount
        self.ds_data_size = cfgDS.data_size
        self.ds_data = cfgDS.data.view
        self.ds_data_header = cfgDS.data_header.view
        self.ds_wid = cfgDS.writer_id.view.cast("q")
        self.ds_rid = cfgDS.reader_id.view.cast("q")

        cfgMetrics = self.manager.cfgMetrics
        self.time_start_analyze = cfgMetrics.time_start_reading.view.cast("q")
        self.engine_complete = cfgMetrics.engine_complete.view

        self.agg_trades = np.ndarray((1000, 4), dtype=int64)
        self.at_max_row = self.agg_trades.shape[0]
        self.at_rid, self.at_wid = 0, 0

    @final
    @error_handler(set_status_code=True)
    def run_engine(self) -> None:
        nPrice: int64
        nQty: int64
        timestamp: int64
        is_sell: int64
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                if task & scs.COMPLETE:
                    if self.complete():
                        self.final_actions()
                        return self.manager.set_proc_sc(
                            scs.COMPLETE, wait_main_task=False
                        )

            if self.ds_wid[0] == self.ds_rid[0]:
                self.alarm_clock()

            if self.ds_wid[0] != self.ds_rid[0]:
                self.get_trade_data()
                while self.at_rid != self.at_wid:
                    nPrice, nQty, timestamp, is_sell = self.agg_trades[self.at_rid, :]

                    if (nPrice < 0) or (nQty < 0) or (timestamp < 0):
                        self.manager.set_proc_sc(
                            code=scs.UNVALID_DATA, wait_main_task=True
                        )
                        continue

                    new_rid = self.at_rid + 1
                    self.at_rid = new_rid if new_rid < self.at_max_row else 0

                    self.engine._update_footprint(nPrice, nQty, timestamp, is_sell)

                    if self.ds_wid[0] != self.ds_rid[0]:
                        if not self.engine._tick_by_tick_analyze:
                            if not self.engine._re_init_session:
                                continue

                    self.time_start_analyze[0] = time.perf_counter_ns()

                    self.engine._analyze_footprint()

                    if self.engine._re_init_session:
                        self.engine._update_footprint(nPrice, nQty, timestamp, is_sell)

                    self.post_update()

    @final
    def complete(self) -> bool:
        return self.ds_wid[0] == self.ds_rid[0] and self.engine._bbox_is_readed()

    @final
    def final_actions(self) -> None:
        self.engine_complete[0] = 1
        self.engine._save_footprint_headers(self.engine.last_idx)
        self.post_final_action()
        self.manager.set_text(
            (
                f"Count Prepped Ticks: {self.engine._counter_ticks} "
                f"Count Signals: {self.engine._sync._count_send_signal}"
            )
        )

    @abstractmethod
    def post_final_action(self) -> None:
        pass

    @abstractmethod
    def alarm_clock(self) -> None:
        pass

    @final
    def get_trade_data(self) -> None:
        cell: int = self.ds_rid[0]
        lrd: int = self.ds_data_header[cell]
        start: int = cell * self.ds_data_size
        new_cell: int = cell + 1
        self.set_trade_data(self.ds_data[start : start + lrd])
        self.ds_rid[0] = new_cell if new_cell < self.ds_cell_amount else 0

    @abstractmethod
    def set_trade_data(self, raw_data: memoryview) -> None:
        pass

    @abstractmethod
    def post_update(self) -> None:
        pass
