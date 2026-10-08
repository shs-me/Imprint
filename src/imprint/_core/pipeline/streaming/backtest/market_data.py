"""Market data streaming module for backtesting pipeline."""

import time
from dataclasses import dataclass, field
from datetime import date
from typing import final

import numpy as np
from numpy import int64
from numpy.lib.npyio import NpzFile
from numpy.typing import NDArray

from imprint._core.constant import AGG_TRADES_DATA_PATH
from imprint._core.ipc import NodeManager, node_handler
from imprint._core.settings import StatusCodes as scs


@final
@dataclass(slots=True)
class MarketDataStream:
    """Streams historical aggregated trade data for backtesting execution.

    Attributes
    ----------
    data_paths : list[str]
        Ordered list of ISO 8601 date strings corresponding to active trading days within the backtest range.
    dataz : NpzFile
        Loaded NumPy compressed archive file handle containing multi-day market data arrays.
    data : ndarray of shape (N, 4)
        Loaded trade array for the current daily partition, containing price, quantity, timestamp, and side flags.
    data_path_id : int
        Index of the currently loaded partition within ``data_paths``.
    read_row : int
        Current row pointer offset within the active ``data`` array.
    max_data_row : int
        Total number of trade rows in the active ``data`` partition.
    """

    manager: NodeManager

    data_paths: list[str] = field(init=False)
    dataz: NpzFile = field(init=False)
    data: NDArray[int64] = field(init=False)
    data_path_id: int = field(default=0, init=False)
    read_row: int = field(default=0, init=False)
    max_data_row: int = field(init=False)

    def __post_init__(self) -> None:
        self.init()

    def init(self) -> None:
        self.dataz = np.load(f"{AGG_TRADES_DATA_PATH}/{self.symbol}.npz")
        self.data_path_id, self.max_data_row, self.read_row = 0, 0, 0
        self.data_paths = self.get_data_paths()
        self.change_data()

    @property
    def symbol(self) -> str:
        return self.manager.cfgCoin.symbol

    @node_handler()
    def run(self) -> None:
        """Execute the streaming loop, dispatching historical trades sequentially to the backtest buffer."""
        _ = self.manager.cfgMarketDataStream
        # - - -
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(
                        scs.EXIT, wait_main_task=False
                    )

                if task & scs.COMPLETE and self.complete():
                    self.manager.complete()
                    continue

                if task & scs.RESET:
                    self.reset()

            if self.read_row >= self.max_data_row:
                if self.complete():
                    self.manager.set_proc_sc(
                        code=scs.DATA_PREPARED, wait_main_task=True
                    )
                    continue
                else:
                    self.change_data()
            else:
                while _.ring_buf.lag_not_is_safe():
                    time.sleep(0.001)

                _.set_data_in_backtest(
                    nPrice=self.data[self.read_row, 0],
                    nQty=self.data[self.read_row, 1],
                    timestamp=self.data[self.read_row, 2],
                    is_sell=self.data[self.read_row, 3],
                )
                self.read_row += 1

    def reset(self) -> None:
        self.init()

    def get_data_paths(self) -> list[str]:
        """Parse the manifest file and filter available daily data partitions by the backtest date range.

        Returns
        -------
        list[str]
            Sorted list of ISO 8601 date strings falling inclusively between ``start_date`` and ``end_date``.

        Raises
        ------
        FileNotFoundError
            If ``data_manifest_path`` does not exist on the filesystem.
        """
        data_manifest_path = (
            f"{AGG_TRADES_DATA_PATH}/{self.symbol}_manifest.txt"
        )
        with open(data_manifest_path) as f:
            dates_str: str = f.read()

        dates: list[date] = sorted(
            [date.fromisoformat(d) for d in dates_str.split(",")[:-1]]
        )
        start_date: date = date.fromisoformat(
            self.manager.cfgSetup.backtest_start_date
        )
        end_date: date = date.fromisoformat(
            self.manager.cfgSetup.backtest_end_date
        )
        need_dates: list[date] = [
            d for d in dates if (start_date <= d <= end_date)
        ]
        return [date.isoformat(d) for d in need_dates]

    def change_data(self) -> None:
        """Advance to the next daily data partition and load its trade array into memory."""
        self.data = self.dataz[self.data_paths[self.data_path_id]]
        self.data_path_id += 1
        self.max_data_row = self.data.shape[0]
        self.read_row = 0

    def complete(self) -> bool:
        """Determine whether all scheduled data partitions have been fully processed.

        Returns
        -------
        bool
            True if all date paths have been consumed, otherwise False.
        """
        return self.data_path_id >= len(self.data_paths)
