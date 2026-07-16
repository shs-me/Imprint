import os
import time
import traceback
from datetime import date
from threading import Thread

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ..... import constant as c


class DataPrepper:
    def __init__(
        self,
        symbol: str,
        startDate: str | None,
        endDate: str | None,
        priceMult: int,
    ) -> None:
        self.symbol: str = symbol.upper()
        self.startDate: str | None = startDate
        self.endDate: str | None = endDate
        self.priceMult: int = priceMult

        self.datadir: str = c.DATA_PATH
        self.typeData: str = c.DATA_TYPE_AGGTRADES_PATH
        self.base_path: str = f"{self.datadir}/{self.typeData}/{self.symbol}"

        self.dfm: NDArray[int64] = np.ndarray((100_000, 2), dtype=int64)
        self.dfmWid: memoryview = memoryview(bytearray(8)).cast("q")
        self.dfmRid: memoryview = memoryview(bytearray(8)).cast("q")
        self.max_row: int = self.dfm.shape[0] - 1
        self.safe_lag: int = round(self.max_row * 0.1)

        self.is_running, self.complete = True, False
        self.error: None | str = None

    def start(self) -> None:
        self.subP: Thread = Thread(target=self.run_prepper_engine, daemon=True)
        self.subP.start()

    def run_prepper_engine(self) -> None:
        try:
            dfmWid, dfmRid, dfm = self.dfmWid, self.dfmRid, self.dfm
            safe_lag, max_row, price_mult = self.safe_lag, self.max_row, self.priceMult
            # - - -
            data_paths: list[str] = self.get_data_paths()
            for path in data_paths:
                with open(file=path, mode="rb") as f:
                    next(f)
                    for line in f:
                        if not self.is_running:
                            break

                        while ((dfmWid[0] - dfmRid[0] + max_row) % max_row) > safe_lag:
                            time.sleep(0)

                        data: list[bytes] = line.split(b",")

                        dfm[dfmWid[0], :] = (
                            round(float(data[1]) * price_mult),
                            int(data[5]),
                        )

                        new_row = dfmWid[0] + 1
                        dfmWid[0] = new_row if (new_row <= max_row) else 0

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
