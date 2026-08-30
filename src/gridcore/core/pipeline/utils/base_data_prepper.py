import os
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from threading import Thread
from typing import final

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ...constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH


@dataclass(slots=True)
class BaseDataPrepper(ABC):
    symbol: str
    start_date: str
    end_date: str

    datadir: str = field(init=False)
    type_data: str = field(init=False)
    base_path: str = field(init=False)
    error: str | None = field(default=None, init=False)
    complete: bool = field(default=False, init=False)
    subP: Thread = field(init=False)

    def __post_init__(self) -> None:
        self.datadir = DATA_PATH
        self.type_data = DATA_TYPE_AGGTRADES_PATH
        self.base_path = f"{self.datadir}/{self.type_data}/{self.symbol}"

    @final
    def start(self) -> None:
        self.subP = Thread(target=self.run_prepper_engine, daemon=True)
        self.subP.start()

    @final
    def run_prepper_engine(self) -> None:
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

    @final
    def get_data_paths(self, endwith: str = ".npy") -> list[str]:
        paths: list[str] = [
            p for p in os.listdir(self.base_path) if p.endswith(endwith)
        ]
        dates: list[date] = sorted([date.fromisoformat(p.split(".")[0]) for p in paths])
        startDate: date = date.fromisoformat(self.start_date)
        endDate: date = date.fromisoformat(self.end_date)
        needDates: list[date] = [d for d in dates if (startDate <= d <= endDate)]
        return [f"{self.base_path}/{date.isoformat(d)}{endwith}" for d in needDates]

    @abstractmethod
    def alarm_clock(self) -> None:
        pass

    @abstractmethod
    def prepper_data(self, line: NDArray[int64]) -> None:
        pass

    @abstractmethod
    def post_prepper(self) -> None:
        pass
