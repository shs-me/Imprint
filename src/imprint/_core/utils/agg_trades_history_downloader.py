import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import numpy as np
from numpy import int64, void
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.utils.base_rest import BaseREST, RestError


class DownloadError(Exception):
    """Raised when historical agg trades download or extraction fails repeatedly."""


@dataclass(slots=True)
class DownloadAggTradesHistory(BaseREST):
    """Download historical Binance aggregated trades ZIP archives and store as compressed `.npz` arrays.

    Parameters
    ----------
    symbol : str
        Trading pair symbol in uppercase (e.g., ``"BTCUSDT"``).
    start_date_str : str
        Start date in ISO 8601 format (``"YYYY-MM-DD"``).
    end_date_str : str
        End date in ISO 8601 format (``"YYYY-MM-DD"``).
    price_mult : int
        Scaling factor multiplier applied to floating-point prices to store as integer representation.
    qty_mult : int
        Scaling factor multiplier applied to floating-point quantities to store as integer representation.

    Attributes
    ----------
    cur_date : date
        Current date being processed in the iteration loop.
    start_date : date
        Parsed start date of the download window.
    end_date : date
        Parsed end date of the download window (capped at yesterday if in the future).
    date_str : str
        ISO 8601 string representation of the current date being processed.
    data_dir : str
        Filesystem directory path where downloaded archives and manifests are stored.
    data_path : str
        Filesystem path to the target compressed `.npz` archive file.
    data_manifest_path : str
        Filesystem path to the tracking manifest text file recording downloaded dates.
    agg_trades_dtype : numpy.dtype
        Structured NumPy dtype definition for parsing raw CSV rows.
    """

    symbol: str = field(init=False)
    start_date_str: str = field(init=False)
    end_date_str: str = field(init=False)
    price_mult: int = field(init=False)
    qty_mult: int = field(init=False)
    cur_date: date = field(init=False)
    start_date: date = field(init=False)
    end_date: date = field(init=False)
    date_str: str = field(init=False)
    data_dir: str = field(init=False)
    data_path: str = field(init=False)
    data_manifest_path: str = field(init=False)

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
        """Initialize REST timeouts, date bounds, and filesystem manifest paths."""
        self.connect_timeout: float | None = 10.0
        self.read_timeout: float | None = None
        self.write_timeout: float | None = None
        self.pool_timeout: float | None = None

        self.data_dir = c.AGG_TRADES_DATA_PATH

    def download(
        self,
        symbol: str,
        start_date_str: str,
        end_date_str: str,
        price_mult: int,
        qty_mult: int,
    ) -> None:
        """Download missing historical daily ZIP archives, extract CSVs, and convert to `.npz` arrays.

        Raises
        ------
        DownloadError
            If downloading a specific daily archive fails three consecutive times.
        """
        self.symbol = symbol
        self.start_date_str = start_date_str
        self.end_date_str = end_date_str
        self.price_mult = price_mult
        self.qty_mult = qty_mult

        self._init_session()

        manifest: str = self.data_manifest
        counter: int = 0
        log_base_url: bool = False
        downloaded_days: list[str] = []
        while self.cur_date <= self.end_date:
            self.date_str = self.cur_date.isoformat()
            base_file: str = f"{self.data_dir}/{self.date_str}"
            zip_path: str = (
                f"{self.data_dir}/{self.symbol}-aggTrades-{self.date_str}.zip"
            )
            csv_path: str = f"{base_file}.csv"

            if self.date_str not in manifest:
                if not log_base_url:
                    self.log(f"Base url: {self.base_url}")
                    log_base_url = True

                endpoint: str = f"{self.symbol}-aggTrades-{self.date_str}.zip"
                self.log(f"Fetching historical trades: {endpoint}")
                endpoint = f"{self.base_url}/{endpoint}"
                try:
                    zip_bytes: bytes = self.send_sync(
                        method="GET", endpoint=endpoint, response_type=bytes
                    )
                except RestError as e:
                    err_msg: str = (
                        f"Failed to download day {self.date_str}: {e}"
                    )
                    if (counter := (counter + 1)) >= 3:
                        raise DownloadError(err_msg)
                    else:
                        self.log(err_msg, level="ERROR")
                        continue

                size: str = self.format_bytes(len(zip_bytes))
                with open(zip_path, "wb") as f:
                    f.write(zip_bytes)

                self._extract_zip(zip_path, csv_path)
                downloaded_days.append(f"{self.date_str}: {size}")

                self._convert_csv_to_npy(csv_path)

            self.cur_date += timedelta(days=1)

        if downloaded_days:
            self.log(f"Downloaded days: {downloaded_days}")

    def _init_session(
        self,
    ) -> None:
        self.base_url: str = f"{c.BASE_UM_AGGTRADES_DAILY_URL}/{self.symbol}"

        self.start_date = date.fromisoformat(self.start_date_str)
        self.end_date = date.fromisoformat(self.end_date_str)

        if self.end_date >= (today := datetime.now(tz=UTC).date()):
            self.end_date = today - timedelta(days=1)

        self.cur_date = self.start_date
        data_path: list[str] = [
            p for p in os.listdir(self.data_dir) if p == f"{self.symbol}.npz"
        ]
        self.data_path = f"{self.data_dir}/{data_path[0]}" if data_path else ""
        self.data_manifest_path = f"{self.data_dir}/{self.symbol}_manifest.txt"
        os.makedirs(self.data_dir, exist_ok=True)

    def _extract_zip(self, zip_path: str, target_csv: str) -> None:
        """Extract the first archived CSV file from a ZIP bundle and remove the ZIP archive.

        Parameters
        ----------
        zip_path : str
            Filesystem path to the downloaded ZIP archive.
        target_csv : str
            Filesystem destination path for the extracted CSV file.
        """
        with zipfile.ZipFile(zip_path, "r") as z:
            extracted_name = z.namelist()[0]
            z.extract(extracted_name, self.data_dir)

        shutil.move(f"{self.data_dir}/{extracted_name}", target_csv)
        if os.path.exists(zip_path):
            os.remove(zip_path)

    def _convert_csv_to_npy(self, csv_path: str) -> None:
        """Parse raw CSV trade records, apply scaling factors, and append to the compressed `.npz` store.

        Parameters
        ----------
        csv_path : str
            Filesystem path to the extracted CSV trades file.
        """
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

        if self.data_path:
            buffer = BytesIO()
            np.save(buffer, trades)
            with zipfile.ZipFile(self.data_path, "a") as z:
                z.writestr(f"{self.date_str}.npy", buffer.getvalue())

        else:
            self.data_path = f"{self.data_dir}/{self.symbol}.npz"
            kwd: dict[str, NDArray[int64]] = {self.date_str: trades}
            np.savez(self.data_path, **kwd)  # pyright: ignore[reportArgumentType]

        self.data_manifest = self.date_str
        os.remove(csv_path)

    @property
    def data_manifest(self) -> str:
        """str: Content of the download tracking manifest file listing completed dates."""
        try:
            with open(self.data_manifest_path, mode="r") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    @data_manifest.setter
    def data_manifest(self, new_data: str) -> None:
        with open(self.data_manifest_path, mode="a") as f:
            f.write(f"{new_data},")
