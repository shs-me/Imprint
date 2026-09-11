import time
from dataclasses import dataclass, field
from datetime import date
from typing import override

import numpy as np
from numpy import uint8
from numpy.lib.npyio import NpzFile
from numpy.typing import NDArray

from imprint._core.constant import AGG_TRADES_DATA_PATH
from imprint._core.ipc import node_handler
from imprint._core.pipeline.streaming.base import Base
from imprint._core.settings import StatusCodes as scs


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

        self.type_data = AGG_TRADES_DATA_PATH
        self.data_path = f"{AGG_TRADES_DATA_PATH}/{self.symbol}.npz"
        self.data_manifest_path = (
            f"{AGG_TRADES_DATA_PATH}/{self.symbol}_manifest.txt"
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
        _ = self.mds.ring_buf
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
                while _.lag_not_is_safe():
                    time.sleep(0.001)

                _.set_data(self.data[self.read_row, :].data)
                self.read_row += 1

    def change_data(self) -> None:
        self.data = self.dataz[self.data_paths[self.data_path_id]].view(uint8)
        self.data_path_id += 1
        self.max_data_row = self.data.shape[0]
        self.read_row = 0

    def complete(self) -> bool:
        return self.data_path_id >= len(self.data_paths)
