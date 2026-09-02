import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import final

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ..models import Converter, Footprint, FPArray


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager

    re_init_session: bool = field(default=True, init=False)
    re_init_idx: bool = field(default=True, init=False)
    re_init_idy: bool = field(default=False, init=False)
    __init_arrays: bool = field(default=True, init=False)

    __save_fp_headers: bool = field(init=False)
    __base_fp_dump_path: str = field(init=False)
    trade_readed_time: memoryview = field(init=False)
    bbox_default_value: NDArray[int64] = field(init=False)
    bbox: NDArray[int64] = field(init=False)
    fp: Footprint = field(init=False)

    def __post_init__(self) -> None:
        cfgFP = self.manager.cfgFootprint
        self.__save_fp_headers = self.manager.cfgFootprint.save_fp_headers

        cfgCoin = self.manager.cfgCoin
        self.__base_fp_dump_path = (
            f"{c.BASE_FOOTPRINT_DUMP_PATH}/{cfgCoin.symbol.upper()}"
        )

        cfgMetrics = self.manager.cfgMetrics
        self.trade_readed_time = cfgMetrics.trade_readed_time.view.cast("q")

        self.fp = Footprint(Converter(cfgCoin=cfgCoin, cfgFP=cfgFP))

    @final
    def init_session(self, nPrice: int64, timestamp: int64) -> None:
        if self.__init_arrays:
            self.__init_array(nPrice=nPrice)
            self.__init_arrays = False

        if self.re_init_idx:
            self.manager.set_proc_sc(code=scs.FP_IDX_FILLED, wait_main_task=False)
            self.__init_idx(nPrice, timestamp)
            self.re_init_idx = False
        else:
            self.manager.set_proc_sc(code=scs.FP_IDY_FILLED, wait_main_task=False)
            self.__init_idy(nPrice)
            self.re_init_idy = False

        self.re_init_session = False
        self.manager.set_proc_sc(scs.FP_RE_INIT, wait_main_task=False)

    @final
    def __init_idx(self, nPrice: int64, timestamp: int64) -> None:
        self.fp.base.fill(0)
        self.fp.state.fill(0)
        self.fp.headers.fill(0)
        self.bbox[:] = self.bbox_default_value

        self.fp.con.init_session(nPrice=nPrice, timestamp=timestamp)
        self.child_init_idx(nPrice, timestamp)

    @abstractmethod
    def child_init_idx(self, nPrice: int64, timestamp: int64) -> None: ...

    @final
    def __init_idy(self, nPrice: int64) -> None:
        self.__init_array(nPrice=nPrice)

    @final
    def __init_array(self, nPrice: int64) -> None:
        if not self.re_init_idy:
            self.fp.con.fp_rows = 2 * (nPrice * 20 // 100 // self.fp.con.scale)
            self.fp.base = FPArray(self.fp.con.fp_rows, self.fp.con.fp_panel_cols)
            self.fp.state = FPArray(self.fp.con.fp_rows, self.fp.con.fp_panel_cols)
            self.bbox = np.zeros((4,), dtype=int64)
            self.bbox_default_value = np.array(
                [self.fp.con.fp_rows, self.fp.con.fp_cols, 0, 0], dtype=int64
            )
        else:
            need_rows: int64 = nPrice * 20 // 100 // self.fp.con.scale
            self.fp.con.fp_rows = self.fp.con.fp_rows + need_rows

            if nPrice > self.fp.con.baseNprice:
                before, after = need_rows, 0
                self.fp.con.center = self.fp.con.center + need_rows
            else:
                before, after = 0, need_rows

            self.fp.base = self.fp.base.pading(int(before), int(after))
            self.fp.state = self.fp.state.pading(int(before), int(after))

        self.child_init_array(nPrice)

    @abstractmethod
    def child_init_array(self, nPrice: int64) -> None: ...

    @final
    def save_footprint_headers(self, last_idx: int) -> None:
        if self.__save_fp_headers:
            os.makedirs(self.__base_fp_dump_path, exist_ok=True)

            start_time: str = self.fp.con.to_strftime(self.fp.con._first_base_timestamp)
            end_time: str = self.fp.con.get_time(idx=last_idx, strftime=True)

            start_date: date = date.fromisoformat(start_time.split("T")[0])
            end_date: date = date.fromisoformat(end_time.split("T")[0])

            paths: list[str] = [
                p.split(".npy")[0]
                for p in os.listdir(self.__base_fp_dump_path)
                if p.endswith(".npy")
            ]
            if paths:
                for p in paths:
                    file_timeframe, file_start_time, file_end_time = p.split("_")
                    if file_timeframe == self.fp.con.timeframe:
                        file_start_date: date = date.fromisoformat(
                            file_start_time.split("T")[0]
                        )
                        file_end_date: date = date.fromisoformat(
                            file_end_time.split("T")[0]
                        )
                        if file_start_date <= start_date <= end_date <= file_end_date:
                            return

            headers_save_path: str = (
                f"{self.__base_fp_dump_path}/"
                f"{self.fp.con.timeframe}"
                f"_{start_time}_{end_time}.npy"
            )
            np.save(headers_save_path, self.fp.headers)
