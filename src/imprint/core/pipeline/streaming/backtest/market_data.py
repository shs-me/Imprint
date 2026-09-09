import time
from dataclasses import dataclass, field
from datetime import date
from typing import override

import numpy as np
from numpy import uint8
from numpy.lib.npyio import NpzFile
from numpy.typing import NDArray

from imprint.core.constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH
from imprint.core.ipc import node_handler
from imprint.core.pipeline.streaming.base import Base
from imprint.core.settings import StatusCodes as scs


@dataclass(slots=True)
class MarketDataStream(Base):
    symbol: str = field(init=False)
    start_date: str = field(init=False)
    end_date: str = field(init=False)

    datadir: str = field(init=False)
    type_data: str = field(init=False)
    data_path: str = field(init=False)
    data_manifest_path: str = field(init=False)

    data_paths: list[str] = field(init=False)
    data_path_id: int = field(default=0, init=False)
    data: NDArray[uint8] = field(init=False)
    dataz: NpzFile = field(init=False)
    read_row: int = field(default=0, init=False)
    max_data_row: int = field(init=False)

    @override
    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.symbol = self.manager.cfgCoin.symbol
        self.start_date = self.manager.cfgSetup.backtest_start_date
        self.end_date = self.manager.cfgSetup.backtest_end_date

        self.datadir = DATA_PATH
        self.type_data = DATA_TYPE_AGGTRADES_PATH
        self.data_path = (
            f"{DATA_PATH}/{DATA_TYPE_AGGTRADES_PATH}/{self.symbol}.npz"
        )
        self.data_manifest_path = (
            f"{DATA_PATH}/{DATA_TYPE_AGGTRADES_PATH}/{self.symbol}_manifest.txt"
        )

        self.data_paths = self.get_data_paths()
        self.dataz = np.load(self.data_path)
        self.change_data()

    def get_data_paths(self) -> list[str]:
        with open(self.data_manifest_path) as f:
            dates_str: str = f.read()

        dates: list[date] = sorted(
            [date.fromisoformat(d) for d in dates_str.split(",")[:-1]]
        )
        start_date: date = date.fromisoformat(self.start_date)
        end_date: date = date.fromisoformat(self.end_date)
        need_dates: list[date] = [
            d for d in dates if (start_date <= d <= end_date)
        ]
        return [date.isoformat(d) for d in need_dates]

    @node_handler()
    def run(self) -> None:
        # Local Links
        wid, rid = self.ds_wid, self.ds_rid
        data, data_size = self.ds_data, self.ds_data_size
        data_header = self.ds_data_header
        cell_amount, safe_lag = self.ds_cell_amount, self.ds_safe_lag
        # - - -
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(
                        scs.EXIT, wait_main_task=False
                    )

                if task & scs.COMPLETE and self.complete():
                    self.final_actions()
                    return self.manager.set_proc_sc(
                        scs.COMPLETE, wait_main_task=False
                    )

            if self.read_row >= self.max_data_row:
                if self.complete():
                    self.manager.set_proc_sc(
                        code=scs.DATA_PREPARED, wait_main_task=True
                    )
                    continue
                else:
                    self.change_data()
            else:
                while self.lag_not_is_safe(
                    wid[0], rid[0], cell_amount, safe_lag
                ) or self.lag_not_is_safe(
                    wid[0], rid[1], cell_amount, safe_lag
                ):
                    time.sleep(0.001)

                raw_data: memoryview = self.data[self.read_row, :].data
                self.set_raw_data(
                    raw_data=raw_data,
                    writer_id=wid,
                    data=data,
                    data_header=data_header,
                    data_size=data_size,
                    cell_amount=cell_amount,
                )
                self.read_row += 1

    def change_data(self) -> None:
        self.data = self.dataz[self.data_paths[self.data_path_id]].view(uint8)
        self.data_path_id += 1
        self.max_data_row = self.data.shape[0]
        self.read_row = 0

    def complete(self) -> bool:
        return self.data_path_id >= len(self.data_paths)
