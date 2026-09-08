import inspect
import json
import os
import shutil
import sys
import traceback
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import wraps
from types import TracebackType
from typing import Any, ParamSpec, TypeVar, cast, final, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.settings import DumpMSG


@final
@dataclass(slots=True)
class DownloadAggTradesHistory:
    symbol: str
    start_date_str: str
    end_date_str: str
    price_mult: int
    qty_mult: int

    start_date: date = field(init=False)
    end_date: date = field(init=False)
    cur_date: date = field(init=False)

    agg_trades_dtype: np.dtype[np.void] = field(
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

    data_dir: str = field(init=False)
    file_name_for_download: str = field(init=False)
    path_for_downloaded_file: str = field(init=False)
    base_file_path: str = field(init=False)
    npy_file_path: str = field(init=False)
    csv_file_path: str = field(init=False)
    file_url_for_download: str = field(init=False)

    def __post_init__(self) -> None:
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
        while self.cur_date <= self.end_date:
            self._init_file_name_path_url()
            if os.path.exists(self.npy_file_path) is False:
                if os.path.exists(self.csv_file_path) is False:
                    self._download_file()
                    self._extract_file_from_archive()

                self._file_data_prepare()

            self.cur_date += timedelta(days=1)

    def _init_file_name_path_url(self) -> None:
        self.file_name_for_download = (
            f"{self.symbol}-aggTrades-{self.cur_date.isoformat()}"
        )

        self.path_for_downloaded_file = (
            f"{self.data_dir}/{self.file_name_for_download}.zip"
        )
        self.base_file_path = f"{self.data_dir}/{self.cur_date.isoformat()}"
        self.npy_file_path = f"{self.base_file_path}.npy"
        self.csv_file_path = f"{self.base_file_path}.csv"

        self.file_url_for_download = f"{c.BASE_UM_AGGTRADES_DAILY_URL}{self.symbol}/{self.file_name_for_download}.zip"

    def _download_file(self) -> None:
        from urllib import request

        dl_file = request.urlopen(self.file_url_for_download)
        length = dl_file.getheader("content-length")
        if length:
            length = int(length)
            blocksize = max(4096, length // 100)
            with open(self.path_for_downloaded_file, "wb") as out_file:
                dl_progress = 0
                while True:
                    if not (buf := dl_file.read(blocksize)):
                        break

                    out_file.write(buf)
                    dl_progress += len(buf)

    def _extract_file_from_archive(self) -> None:
        with zipfile.ZipFile(self.path_for_downloaded_file, "r") as zip_ref:
            file_path_ = zip_ref.extract(zip_ref.namelist()[0])

        shutil.move(file_path_, self.csv_file_path)
        os.remove(self.path_for_downloaded_file)

    def _file_data_prepare(self) -> None:
        arr: NDArray[np.void] = np.genfromtxt(
            fname=self.csv_file_path,
            usecols=(1, 2, 5, 6),
            dtype=self.agg_trades_dtype,
            skip_header=1,
            delimiter=",",
        )
        agg_trades: NDArray[int64] = np.ndarray(
            shape=(arr.shape[0], 4), dtype=int64
        )
        agg_trades[:, 0] = (arr["price"] * self.price_mult).astype(int64)
        agg_trades[:, 1] = (arr["qty"] * self.qty_mult).astype(int64)
        agg_trades[:, 2] = arr["timestamp"].astype(int64)
        agg_trades[:, 3] = arr["is_buyer_maker"].astype(int64)

        np.save(self.npy_file_path, agg_trades)
        os.remove(self.csv_file_path)


class DebugEncoder(json.JSONEncoder):
    """Custom JSON encoder handling set, range, datetime, and non-serializable objects."""

    @override
    def default(self, o: Any):
        if isinstance(o, (set, range)):
            return list(o)  # pyright: ignore[reportUnknownArgumentType]
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "__dict__"):
            return f"Object: {type(o).__name__}"
        return f"<Non-serializable: {type(o).__name__}>"


@final
@dataclass(slots=True)
class DumpException:
    exc_type: type[BaseException] | None = field(default=None, init=False)
    exc_value: BaseException | None = field(default=None, init=False)
    exc_tb: TracebackType | None = field(default=None, init=False)
    dump_msg: DumpMSG = field(
        default_factory=lambda: {
            "timestamp": "",
            "type": "",
            "message": "",
            "traceback": [],
            "locals": {},
        },
        init=False,
    )

    def dump_exception(self) -> None:
        self._get_exc_info()
        self._create_dump_msg()
        try:
            with open(file=c.EXC_DUMP_PATH, mode="a", encoding="utf-8") as f:
                json.dump(
                    obj=self.dump_msg,
                    fp=f,
                    ensure_ascii=False,
                    indent=4,
                    cls=DebugEncoder,
                )
                f.write("\n" + "=" * 50 + "\n")

        except Exception as final_err:
            sys.stderr.write(
                f"Critical error during dump_exception: {final_err}\n"
            )

    def _get_exc_info(self) -> None:
        self.exc_type, self.exc_value, self.exc_tb = sys.exc_info()

    def _create_dump_msg(self) -> None:
        self.dump_msg["timestamp"] = datetime.now(tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.dump_msg["type"] = (
            self.exc_type.__name__ if self.exc_type else "UnknownError"
        )
        self.dump_msg["message"] = str(self.exc_value)
        self.dump_msg["traceback"] = traceback.format_exception(
            self.exc_type, self.exc_value, self.exc_tb
        )
        self.dump_msg["locals"] = {}

        if self.exc_tb:
            while self.exc_tb.tb_next:
                self.exc_tb = self.exc_tb.tb_next

            frame_locals: dict[str, Any] = self.exc_tb.tb_frame.f_locals
            for var_name, var_val in frame_locals.items():
                try:
                    self.dump_msg["locals"][var_name] = self._process_value(
                        var_val
                    )
                except Exception as e:
                    self.dump_msg["locals"][var_name] = (
                        f"<Error processing value: {e}>"
                    )

    def _process_value(self, val: Any, max_len: int = 100) -> Any:
        if isinstance(val, memoryview):
            return {
                "type": "memoryview",
                "format": val.format,
                "shape": val.shape,
                "nbytes": val.nbytes,
                "readonly": val.readonly,
                "obj_type": type(val.obj).__name__,
            }

        if isinstance(val, (list, tuple, set)):
            val = cast(list[Any] | tuple[Any] | set[Any], val)
            content = list(val)[:10]
            suffix = "..." if len(val) > 10 else ""
            return f"{type(val).__name__}(len={len(val)}): {content}{suffix}"

        if isinstance(val, dict):
            val = cast(dict[Any, Any], val)
            return {
                "__info__": f"dict(len={len(val)})",
                "keys": list(val.keys())[:20],
            }

        if isinstance(val, (str, bytes)):
            if len(val) > max_len:
                preview = val[:max_len]
                return f"{type(val).__name__}(len={len(val)}): {preview!r}..."
            return val

        if inspect.isfunction(val) or inspect.isclass(val):
            return f"<{type(val).__name__}: {val.__name__}>"

        if hasattr(val, "__dict__"):
            attrs: dict[Any, Any] = {}
            for k, v in val.__dict__.items():
                if not k.startswith("_"):
                    if isinstance(v, (int, float, str, bool, type(None))):
                        attrs[k] = v
                    else:
                        attrs[k] = f"<{type(v).__name__}>"

            val = cast(dict[Any, Any], val)
            return {"object": type(val).__name__, "attributes": attrs}

        return repr(val)


P = ParamSpec("P")
R = TypeVar("R")


def error_handler():
    def decorator(func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            dumper: DumpException = DumpException()
            try:
                return func(*args, **kwargs)
            except Exception:
                dumper.dump_exception()

        return wrapper

    return decorator
