"""Abstract base class for asynchronous CSV tick data prefetching."""

import os
import traceback
from abc import ABC, abstractmethod
from datetime import date
from threading import Thread

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ...constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH


class BaseDataPrepper(ABC):
    """Threaded worker for reading historical tick CSV data from disk.

    Attributes:
        symbol (str): Target trading symbol.
        start_date (str): Backtest start date ISO string.
        end_date (str): Backtest end date ISO string.
        complete (bool): Execution completion indicator.
        error (str | None): Captured exception message if pipeline fails.
    """

    def __init__(self, symbol: str, start_date: str, end_date: str) -> None:

        self.symbol: str = symbol.upper()
        self.start_date: str = start_date
        self.end_date: str = end_date

        self.datadir: str = DATA_PATH
        self.type_data: str = DATA_TYPE_AGGTRADES_PATH
        self.base_path: str = f"{self.datadir}/{self.type_data}/{self.symbol}"

        self.error: str | None = None
        self.complete: bool = False

    def start(self) -> None:
        """Launches background prepper thread in daemon mode."""

        self.subP: Thread = Thread(target=self.run_prepper_engine, daemon=True)
        self.subP.start()

    def run_prepper_engine(self) -> None:
        """Main loop iterating through NPY files, parsing rows, and executing pipeline callbacks."""

        try:
            data_paths: list[str] = self.get_data_paths()
            for path in data_paths:
                arr: NDArray[int64] = np.load(file=path, mmap_mode="r")
                max_row: int = arr.shape[0]
                for row in range(max_row):
                    if not self.complete:
                        line: NDArray[int64] = arr[row, :]
                        self.alarm_clock()
                        self.prepper_data(line)
                    else:
                        break

            self.post_prepper()
            self.complete = True

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.complete = True

    def get_data_paths(self, endwith: str = ".npy") -> list[str]:
        """Filters and returns sorted list of NPY file paths matching target date scope.

        Returns:
            list[str]: Absolute file paths to target NPY files.
        """

        paths: list[str] = [
            p for p in os.listdir(self.base_path) if p.endswith(endwith)
        ]
        dates: list[date] = sorted([date.fromisoformat(p.split(".")[0]) for p in paths])
        startDate: date = (
            dates[0]
            if (self.start_date is None)
            else date.fromisoformat(self.start_date)
        )
        endDate: date = (
            dates[-1] if (self.end_date is None) else date.fromisoformat(self.end_date)
        )
        needDates: list[date] = [d for d in dates if (startDate <= d <= endDate)]
        return [f"{self.base_path}/{date.isoformat(d)}{endwith}" for d in needDates]

    @abstractmethod
    def alarm_clock(self) -> None:
        """Abstract throttle hook invoked when output buffer reaches high-water threshold."""

        pass

    @abstractmethod
    def prepper_data(self, line: NDArray[int64]) -> None:
        """Abstract row parser hook invoked for each NPY line."""

        pass

    @abstractmethod
    def post_prepper(self) -> None:
        """Abstract post-processing teardown hook invoked upon completing file iteration."""

        pass
