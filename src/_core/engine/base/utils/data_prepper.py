import os
import struct
import time
import traceback
from collections import deque
from datetime import date
from threading import Thread

from ....constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH


class DataPrepper:
    def __init__(self, symbol: str, startDate: str | None, endDate: str | None) -> None:
        self.symbol: str = symbol.upper()
        self.startDate, self.endDate = startDate, endDate

        self.datadir: str = DATA_PATH
        self.typeData: str = DATA_TYPE_AGGTRADES_PATH
        self.base_path: str = f"{self.datadir}/{self.typeData}/{self.symbol}"

        self.queue: deque = deque(maxlen=10000)

        self.is_running, self.complete = True, False
        self.error: None | str = None

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
                        data: list[bytes] = line.split(b",")
                        self.queue.append(self.get_obj(data))

            self.complete = True

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.is_running = False

    def get_data_paths(self) -> list[str]:
        paths: list[str] = [p for p in os.listdir(self.base_path) if p.endswith(".csv")]
        dates: list[date] = sorted([date.fromisoformat(p.split(".")[0]) for p in paths])
        startDate: date = (
            dates[0] if (self.startDate is None) else date.fromisoformat(self.startDate)
        )
        endDate: date = (
            dates[-1] if (self.endDate is None) else date.fromisoformat(self.endDate)
        )
        needDates: list[date] = [d for d in dates if (startDate <= d <= endDate)]
        return [f"{self.base_path}/{date.isoformat(d)}.csv" for d in needDates]

    def alarm_clock(self) -> None:
        while len(self.queue) == self.queue.maxlen:
            time.sleep(0)

    def get_obj(self, data: list[bytes]) -> bytes:
        return struct.pack(
            "@ddq?",
            float(data[1]),
            float(data[2]),
            int(data[5]),
            b"true" in data[6],
        )
