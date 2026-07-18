import ctypes
import os
import signal
import sys
import zipfile
from datetime import date, timedelta
from urllib import request

from .. import constant as c


def generate_ctrl_c_event(pids: list[int]) -> None:
    if sys.platform == "win32":
        [ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, pid) for pid in pids]
    elif sys.platform == "linux":
        [os.kill(pid, signal.SIGINT) for pid in pids]


def to_date(iso_f_dates: list[str]):
    return [date.fromisoformat(d) for d in iso_f_dates]


def download_aggTrade_hist_daily_data(
    symbol: str, startDate: date, endDate: date
) -> bool:
    base_path = f"{c.DATA_PATH}/{c.DATA_TYPE_AGGTRADES_PATH}/{symbol.upper()}"
    os.makedirs(base_path, exist_ok=True)

    endDate = endDate if date.today() > endDate else date.today()
    curDate = startDate
    while curDate < endDate:
        file_name = f"{symbol.upper()}-aggTrades-{curDate.isoformat()}"
        zip_path = f"{base_path}/{file_name}.zip"
        file_path = f"{base_path}/{curDate.isoformat()}.csv"
        if os.path.exists(file_path) is False:
            url = f"{c.BASE_UM_AGGTRADES_DAILY_URL}{symbol.upper()}/{file_name}.zip"
            download_file(url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                file_path_ = zip_ref.extract(zip_ref.namelist()[0])

            os.rename(file_path_, file_path)
            os.remove(zip_path)

        curDate += timedelta(days=1)

    return True


def download_file(url: str, path: str) -> None:
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
