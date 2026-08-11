import os

import numpy as np

from ... import constant as c
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from .base import Writer


class Extented(Writer):
    def __init__(self, manager: NodeManager) -> None:
        super().__init__(manager)

        self.base_fp_dump_path: str = (
            f"{c.BASE_FOOTPRINT_DUMP_PATH}/{manager.cfgCoin.symbol.upper()}"
        )

    def bbox_is_read(self) -> bool:
        return bool(np.all(self.bbox[:] == self.bbox_default_value))

    def pre_re_init(self) -> None:
        self.wait_read_bbox()
        self.save_fp_headers_array()
        self.set_proc_sc(scs.FP_RE_INIT, wait_main_task=True)

    def save_fp_headers_array(self) -> None:
        if self.save_fp_headers:
            os.makedirs(self.base_fp_dump_path, exist_ok=True)
            headers_save_path = (
                f"{self.base_fp_dump_path}/{self.con.get_time(idx=0, strftime=True)}"
            )
            if not os.path.exists(headers_save_path):
                np.save(headers_save_path, self.headers)

    def final_actions(self) -> None:
        if (self.last_idx[0] & ~1) == (self.manager.cfgFootprint.fp_cols - 1 & ~1):
            self.save_fp_headers_array()
