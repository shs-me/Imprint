import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import numpy as np
from numpy import int64, void
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.utils.base_rest import BaseREST, RestError


class DownloadError(Exception): ...


@dataclass(slots=True)
class DownloadAggTradesHistory(BaseREST):
    symbol: str
    start_date_str: str
    end_date_str: str
    price_mult: int
    qty_mult: int

    cur_date: date = field(init=False)
    start_date: date = field(init=False)
    end_date: date = field(init=False)
    data_dir: str = field(init=False)

    agg_trades_dtype: np.dtype[void] = field(
        default_factory=lambda: np.dtype(
            [
                ("price", "float64"),
                ("qty", "float64"),
                ("timestamp", "int64"),
                ("is_buyer_maker", "bool_"),
            ]
        ),
        init=False,
    )

    def __post_init__(self) -> None:
        self.connect_timeout: float | None = 10.0
        self.read_timeout: float | None = None
        self.write_timeout: float | None = None
        self.pool_timeout: float | None = None

        self.base_url: str = f"{c.BASE_UM_AGGTRADES_DAILY_URL}{self.symbol}"

        self.start_date = date.fromisoformat(self.start_date_str)
        self.end_date = date.fromisoformat(self.end_date_str)

        if self.end_date >= (today := datetime.now(tz=UTC).date()):
            self.end_date = today - timedelta(days=1)

        self.cur_date = self.start_date
        self.data_dir = (
            f"{c.DATA_PATH}/{c.DATA_TYPE_AGGTRADES_PATH}/{self.symbol}"
        )
        os.makedirs(self.data_dir, exist_ok=True)

    def download(self) -> None:
        """Downloads historical archives and converts them to binary .npy format."""
        counter: int = 0
        log_base_url: bool = False
        downloaded_days: list[str] = []
        while self.cur_date <= self.end_date:
            date_str: str = self.cur_date.isoformat()
            base_file: str = f"{self.data_dir}/{date_str}"
            npy_path: str = f"{base_file}.npy"
            zip_path: str = (
                f"{self.data_dir}/{self.symbol}-aggTrades-{date_str}.zip"
            )
            csv_path: str = f"{base_file}.csv"

            if not os.path.exists(npy_path):
                if not os.path.exists(csv_path):
                    if not log_base_url:
                        self.log(f"Base url: {self.base_url}")
                        log_base_url = True

                    endpoint: str = f"{self.symbol}-aggTrades-{date_str}.zip"
                    self.log(f"Fetching historical trades: {endpoint}")
                    endpoint = f"{self.base_url}/{endpoint}"
                    try:
                        zip_bytes = self.send_sync(
                            method="GET", endpoint=endpoint, response_type=bytes
                        )
                    except RestError as e:
                        counter += 1
                        err_msg: str = f"Failed to download day {date_str}: {e}"
                        if counter >= 3:
                            raise DownloadError(err_msg)
                        else:
                            self.log(err_msg, level="ERROR")
                            continue

                    size: str = self.format_bytes(len(zip_bytes))
                    with open(zip_path, "wb") as f:
                        f.write(zip_bytes)

                    self._extract_zip(zip_path, csv_path)
                    downloaded_days.append(f"{date_str}: {size}")

                self._convert_csv_to_npy(csv_path, npy_path)

            self.cur_date += timedelta(days=1)

        if downloaded_days:
            self.log(f"Downloaded days: {downloaded_days}")

    def _extract_zip(self, zip_path: str, target_csv: str) -> None:
        with zipfile.ZipFile(zip_path, "r") as z:
            extracted_name = z.namelist()[0]
            z.extract(extracted_name, self.data_dir)

        shutil.move(f"{self.data_dir}/{extracted_name}", target_csv)
        if os.path.exists(zip_path):
            os.remove(zip_path)

    def _convert_csv_to_npy(self, csv_path: str, npy_path: str) -> None:
        arr: NDArray[void] = np.genfromtxt(
            csv_path,
            usecols=(1, 2, 5, 6),
            dtype=self.agg_trades_dtype,
            skip_header=1,
            delimiter=",",
        )
        trades: NDArray[int64] = np.ndarray(
            shape=(arr.shape[0], 4), dtype=int64
        )
        trades[:, 0] = (arr["price"] * self.price_mult).astype(int64)
        trades[:, 1] = (arr["qty"] * self.qty_mult).astype(int64)
        trades[:, 2] = arr["timestamp"].astype(int64)
        trades[:, 3] = arr["is_buyer_maker"].astype(int64)

        np.save(npy_path, trades)
        os.remove(csv_path)
