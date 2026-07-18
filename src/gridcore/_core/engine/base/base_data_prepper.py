import os
import traceback
from abc import ABC, abstractmethod
from datetime import date
from threading import Thread

from ...constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH


class BaseDataPrepper(ABC):
    def __init__(self, symbol: str, start_date: str, end_date: str) -> None:
        self.symbol: str = symbol.upper()
        self.start_date: str = start_date
        self.end_date: str = end_date

        self.datadir: str = DATA_PATH
        self.type_data: str = DATA_TYPE_AGGTRADES_PATH
        self.base_path: str = f"{self.datadir}/{self.type_data}/{self.symbol}"

        self.error: str | None = None
        self.is_running, self.complete = True, False

    def start(self) -> None:
        self.subP: Thread = Thread(target=self.run_prepper_engine, daemon=True)
        self.subP.start()

    def run_prepper_engine(self) -> None:
        try:
            data_paths: list[str] = self.get_data_paths()
            for path in data_paths:
                with open(file=path, mode="rb") as f:
                    next(f)
                    for line in f:
                        if not self.is_running:
                            break

                        self.alarm_clock()
                        self.prepper_data(line)

            self.complete = True

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.is_running = False

    def get_data_paths(self) -> list[str]:
        paths: list[str] = [p for p in os.listdir(self.base_path) if p.endswith(".csv")]
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
        return [f"{self.base_path}/{date.isoformat(d)}.csv" for d in needDates]

    @abstractmethod
    def alarm_clock(self) -> None:
        pass

    @abstractmethod
    def prepper_data(self, data: bytes) -> None:
        pass
