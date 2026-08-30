import os
from abc import ABC
from dataclasses import dataclass, field
from datetime import date
from typing import final

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ..models.converter import Converter


@dataclass
class Base(ABC):
    _manager: NodeManager

    __init_arrays: bool = field(default=True, init=False)
    _re_init_session: bool = field(default=True, init=False)
    _re_init_idx: bool = field(default=True, init=False)
    _re_init_idy: bool = field(default=False, init=False)

    __save_fp_headers: bool = field(init=False)
    __base_fp_dump_path: str = field(init=False)
    _footprint: NDArray[int64] = field(init=False)
    _headers: NDArray[int64] = field(init=False)
    _bbox: NDArray[int64] = field(init=False)
    _bbox_default_value: NDArray[int64] = field(init=False)
    con: Converter = field(init=False)

    def __post_init__(self) -> None:
        cfgFP = self._manager.cfgFootprint
        self.__save_fp_headers = self._manager.cfgFootprint.save_fp_headers

        cfgCoin = self._manager.cfgCoin
        self.__base_fp_dump_path = (
            f"{c.BASE_FOOTPRINT_DUMP_PATH}/{cfgCoin.symbol.upper()}"
        )

        self.con = Converter(cfgCoin=cfgCoin, cfgFP=cfgFP)

        self.__init_arrays = True
        self._re_init_session = True
        self._re_init_idx = True
        self._re_init_idy = False

    def _init_array(self, nPrice: int64) -> None:
        if not self._re_init_idy:
            self.con.fp_rows = 2 * (nPrice * 20 // 100 // self.con.scale)
            self._footprint = np.zeros(
                shape=(self.con.fp_rows, self.con.fp_panel_cols), dtype=int64
            )
            self._headers = np.zeros(
                shape=(self.con.chart_range * self.con.bar_count, c.BH_ConstantCount),
                dtype=int64,
            )
            self._bbox = np.zeros((4,), dtype=int64)
            self._bbox_default_value = np.array(
                [self.con.fp_rows, self.con.fp_cols, 0, 0], dtype=int64
            )
        else:
            need_rows: int64 = nPrice * 20 // 100 // self.con.scale
            self.con.fp_rows = self.con.fp_rows + need_rows
            self.con.center = self.con.fp_rows // 2
            before, after = (
                (need_rows, 0) if (nPrice > self.con.baseNprice) else (0, need_rows)
            )
            self._footprint = np.pad(
                array=self._footprint, pad_width=((int(before), int(after)), (0, 0))
            )

    def _init_session(self, nPrice: int64, timestamp: int64) -> None:
        if self.__init_arrays:
            self._init_array(nPrice=nPrice)
            self.__init_arrays = False

        if self._re_init_idx:
            self._manager.set_proc_sc(code=scs.FP_IDX_FILLED, wait_main_task=False)
            self._init_idx(nPrice, timestamp)
            self._re_init_idx = False
        else:
            self._manager.set_proc_sc(code=scs.FP_IDY_FILLED, wait_main_task=False)
            self._init_idy(nPrice)
            self._re_init_idy = False

        self._re_init_session = False
        self._manager.set_proc_sc(scs.FP_RE_INIT, wait_main_task=False)

    def _init_idx(self, nPrice: int64, timestamp: int64) -> None:
        self._footprint.fill(0)
        self._headers.fill(0)
        self._bbox[:] = self._bbox_default_value

        self.con.init_session(nPrice=nPrice, timestamp=timestamp)

    def _init_idy(self, nPrice: int64) -> None:
        self._init_array(nPrice=nPrice)

    @final
    def _save_footprint_headers(self, last_idx: int) -> None:
        if self.__save_fp_headers:
            os.makedirs(self.__base_fp_dump_path, exist_ok=True)

            start_time: str = self.con.to_strftime(self.con._first_base_timestamp)
            end_time: str = self.con.get_time(idx=last_idx, strftime=True)

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
                    if file_timeframe == self.con.timeframe:
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
                f"{self.con.timeframe}"
                f"_{start_time}_{end_time}.npy"
            )
            np.save(headers_save_path, self._headers)
