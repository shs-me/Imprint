import os
from abc import ABC

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ..models.converter import Converter


class Base(ABC):
    def __init__(self, manager: NodeManager) -> None:
        self._manager: NodeManager = manager
        self._set_proc_sc = manager.set_proc_sc

        cfgFP = manager.cfgFootprint
        self._tick_by_tick_analyze: bool = cfgFP.tick_by_tick_analyze
        self.__save_fp_headers: bool = cfgFP.save_fp_headers

        self.__base_fp_dump_path: str = (
            f"{c.BASE_FOOTPRINT_DUMP_PATH}/{manager.cfgCoin.symbol.upper()}"
        )

        self._init_array()

        self.con: Converter = Converter(
            footprint=self._footprint,
            headers=self._headers,
            cfgCoin=manager.cfgCoin,
            cfgFP=cfgFP,
        )
        self._re_init_session: bool = True

    def _init_array(self) -> None:
        cfgFP = self._manager.cfgFootprint
        self._footprint: NDArray[int64] = np.zeros(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols),
            dtype=int64,
        )
        self._headers: NDArray[int64] = np.zeros(
            shape=(cfgFP.bar_count, c.BH_ConstantCount), dtype=int64
        )
        self._bbox: NDArray[int64] = np.zeros((4,), dtype=int64)
        self._bbox_default_value: NDArray[int64] = np.array(
            [cfgFP.fp_rows, cfgFP.fp_cols, 0, 0], dtype=int64
        )

    def _init_session(self, nPrice: int, timestamp: int) -> None:
        self.__save_fp_headers_array()

        self._footprint.fill(0)
        self._headers.fill(0)
        self._bbox[:] = self._bbox_default_value

        self.con.init_session(
            nPrice=(nPrice),
            timestamp=(timestamp),
        )
        self._re_init_session = False
        self._set_proc_sc(scs.FP_RE_INIT, wait_main_task=False)

    def __save_fp_headers_array(self) -> None:
        if self.__save_fp_headers and self._headers[-1, 0] != 0:
            os.makedirs(self.__base_fp_dump_path, exist_ok=True)
            headers_save_path = (
                f"{self.__base_fp_dump_path}/{self.con.get_time(idx=0, strftime=True)}"
            )
            if not os.path.exists(headers_save_path):
                np.save(headers_save_path, self._headers)
