import os
import shutil
import zipfile
from dataclasses import dataclass, field

import numpy as np
from numpy import int64, void
from numpy.typing import NDArray

import imprint._core.constant as c
from imprint._core.settings import LogLevel
from imprint._core.utils import TradesLoader
from imprint._core.utils.base import TradesArray
from imprint._core.utils.base_rest import RestError


@dataclass(slots=True)
class BinanceAggTradesLoader(TradesLoader):
    """Download historical Binance aggregated trades ZIP archives and store as compressed `.npz` arrays."""

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

    def init_session(self) -> None:
        TradesLoader.init_session(self)

        self.base_url: str = f"{c.BINANCE_UM_AGGTRADES_DAILY_URL}/{self.symbol}"
        self.log(f"Base url: {self.base_url}")

    def prepare_trades(self) -> TradesArray | None:
        base_file: str = f"{self.data_dir}/{self.date_str}"
        zip_path: str = (
            f"{self.data_dir}/{self.symbol}-aggTrades-{self.date_str}.zip"
        )
        csv_path: str = f"{base_file}.csv"
        endpoint: str = f"{self.symbol}-aggTrades-{self.date_str}.zip"
        self.log(f"Fetching historical trades: {endpoint}")
        endpoint = f"{self.base_url}/{endpoint}"
        try:
            zip_bytes: bytes = self.send_sync(
                method="GET", endpoint=endpoint, response_type=bytes
            )
        except RestError as e:
            return self.log(
                f"Failed to download day {self.date_str}: {e}", LogLevel.ERROR
            )

        with open(zip_path, "wb") as f:
            f.write(zip_bytes)

        self._extract_zip(zip_path, csv_path)
        return self._convert_csv_to_npy(csv_path)

    def _extract_zip(self, zip_path: str, target_csv: str) -> None:
        with zipfile.ZipFile(zip_path, "r") as z:
            extracted_name = z.namelist()[0]
            z.extract(extracted_name, self.data_dir)

        shutil.move(f"{self.data_dir}/{extracted_name}", target_csv)
        if os.path.exists(zip_path):
            os.remove(zip_path)

    def _convert_csv_to_npy(self, csv_path: str) -> TradesArray:
        arr: NDArray[void] = np.genfromtxt(
            csv_path,
            usecols=(1, 2, 5, 6),
            dtype=self.agg_trades_dtype,
            skip_header=1,
            delimiter=",",
        )
        trades: TradesArray = TradesArray(arr.shape[0])
        trades[:, 0] = (arr["price"] * self.price_mult).astype(int64)
        trades[:, 1] = (arr["qty"] * self.qty_mult).astype(int64)
        trades[:, 2] = arr["timestamp"].astype(int64)
        trades[:, 3] = arr["is_buyer_maker"].astype(int64)
        os.remove(csv_path)
        return trades
