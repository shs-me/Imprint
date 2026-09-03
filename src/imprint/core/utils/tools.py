import json
import os
from datetime import date, datetime, timedelta
from typing import Any, override

from .. import constant as c


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


def dump_exception() -> None:
    import sys
    import traceback
    from types import TracebackType

    exc_type, exc_value, exc_tb = sys.exc_info()

    data: dict[str, str | list[str] | dict[str, Any]] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": exc_type.__name__ if exc_type else "UnknownError",
        "message": str(exc_value),
        "traceback": traceback.format_exception(exc_type, exc_value, exc_tb),
        "locals": {},
    }

    tb: TracebackType | None = exc_tb
    if tb:
        while tb.tb_next:
            tb = tb.tb_next

        frame_locals = tb.tb_frame.f_locals
        for var_name, var_val in frame_locals.items():
            if isinstance(data["locals"], dict):
                try:
                    data["locals"][var_name] = process_value(var_val)
                except Exception as e:
                    data["locals"][var_name] = f"<Error processing value: {e}>"

    try:
        with open(file=c.EXC_DUMP_PATH, mode="a", encoding="utf-8") as f:
            json.dump(obj=data, fp=f, ensure_ascii=False, indent=4, cls=DebugEncoder)
            f.write("\n" + "=" * 50 + "\n")

    except Exception as final_err:
        sys.stderr.write(f"Critical error during dump_exception: {final_err}\n")


def process_value(val: Any, max_len: int = 100) -> Any:
    import inspect

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
        content: list[Any] = list(val)[:10]
        suffix = "..." if len(val) > 10 else ""
        return f"{type(val).__name__}(len={len(val)}): {content}{suffix}"

    if isinstance(val, dict):
        return {"__info__": f"dict(len={len(val)})", "keys": list(val.keys())[:20]}

    if isinstance(val, (str, bytes)):
        if len(val) > max_len:
            preview = val[:max_len]
            return f"{type(val).__name__}(len={len(val)}): {preview!r}..."
        return val

    if inspect.isfunction(val) or inspect.isclass(val):
        return f"<{type(val).__name__}: {val.__name__}>"

    if hasattr(val, "__dict__"):
        attrs = {}
        for k, v in val.__dict__.items():
            if not k.startswith("_"):
                if isinstance(v, (int, float, str, bool, type(None))):
                    attrs[k] = v
                else:
                    attrs[k] = f"<{type(v).__name__}>"
        return {"object": type(val).__name__, "attributes": attrs}

    return repr(val)


def to_date(iso_f_dates: list[str]):
    """Converts list of ISO format date strings into datetime.date objects."""

    return [date.fromisoformat(d) for d in iso_f_dates]


def download_agg_trades_history(
    symbol: str, start_date: date, end_date: date, price_mult: int, qty_mult: int
) -> bool:
    import zipfile

    import numpy as np
    from numpy import int64
    from numpy.typing import NDArray

    agg_trades_dtype = np.dtype(
        [
            ("price", "float64"),
            ("qty", "float64"),
            ("timestamp", "int64"),
            ("is_buyer_maker", "bool_"),
        ]
    )

    symbol = symbol.upper()
    dir: str = f"{c.DATA_PATH}/{c.DATA_TYPE_AGGTRADES_PATH}/{symbol}"

    os.makedirs(dir, exist_ok=True)

    if end_date >= (today := date.today()):
        end_date = today - timedelta(days=1)

    cur_date: date = start_date
    while cur_date <= end_date:
        file_name_for_download: str = f"{symbol}-aggTrades-{cur_date.isoformat()}"
        path_for_downloaded_file: str = f"{dir}/{file_name_for_download}.zip"

        base_file_path: str = f"{dir}/{cur_date.isoformat()}"
        npy_file_path: str = f"{base_file_path}.npy"
        csv_file_path: str = f"{base_file_path}.csv"

        if os.path.exists(npy_file_path) is False:
            if os.path.exists(csv_file_path) is False:
                url: str = f"{c.BASE_UM_AGGTRADES_DAILY_URL}{symbol}/{file_name_for_download}.zip"

                download_file(url, path_for_downloaded_file)

                with zipfile.ZipFile(path_for_downloaded_file, "r") as zip_ref:
                    file_path_ = zip_ref.extract(zip_ref.namelist()[0])

                os.rename(file_path_, csv_file_path)
                os.remove(path_for_downloaded_file)

            arr: NDArray[np.void] = np.genfromtxt(
                fname=csv_file_path,
                usecols=(1, 2, 5, 6),
                dtype=agg_trades_dtype,
                skip_header=1,
                delimiter=",",
            )
            agg_trades: NDArray[int64] = np.ndarray(
                shape=(arr.shape[0], 4), dtype=int64
            )
            agg_trades[:, 0] = (arr["price"] * price_mult).astype(int64)
            agg_trades[:, 1] = (arr["qty"] * qty_mult).astype(int64)
            agg_trades[:, 2] = arr["timestamp"].astype(int64)
            agg_trades[:, 3] = arr["is_buyer_maker"].astype(int64)

            np.save(npy_file_path, agg_trades)
            os.remove(csv_file_path)

        cur_date += timedelta(days=1)

    return True


def download_file(url: str, path: str) -> None:
    """Downloads file from target URL to disk path with progress streaming."""
    from urllib import request

    dl_file = request.urlopen(url)
    length = dl_file.getheader("content-length")
    if length:
        length = int(length)
        blocksize = max(4096, length // 100)
        with open(path, "wb") as out_file:
            dl_progress = 0
            while True:
                if not (buf := dl_file.read(blocksize)):
                    break

                out_file.write(buf)
                dl_progress += len(buf)
