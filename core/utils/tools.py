import os
from datetime import date
from urllib import error, request

import core.constant as ct


def get_configs_kwargs(*args) -> dict[str, object]:
    kwargs = {}
    for obj in args:
        name = str(obj.__class__).split(".")[-1].removesuffix("'>")
        kwargs[name] = obj

    return kwargs


def to_date(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def check_dirs(path: str) -> None:
    dirs: list[str] = path.split("/")
    dirP: str = ""
    if os.path.exists((dirP := dirs[0])) is False:
        os.mkdir(dirP)

    for _ in range(len(dirs[1:])):
        if os.path.exists(dirP := f"{dirP}/{dirs[_]}") is False:
            os.mkdir(dirP)


def download_file(url: str, path: str) -> None:
    try:
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

    except error.HTTPError:
        pass


def download_aggTrade_hist_data(symbol: str, startDate: date, endDate: date) -> bool:
    base_path = f"{ct.DATA_PATH}/{ct.DATA_TYPE_AGGTRADES_PATH}/{symbol.upper()}"
    check_dirs(base_path)

    date_ = startDate
    endDate = endDate if date.today() > endDate else date.today()
    while date_ != endDate:
        file_name = f"{symbol.upper()}-aggTrades-{date_.isoformat()}.zip"
        path = f"{base_path}/{file_name}"
        if os.path.exists(path) is False:
            url = f"{ct.BASE_UM_AGGTRADES_DAILY_URL}{symbol.lower()}/{file_name}"
            download_file(url, path)
            try:
                date_ = date_.replace(day=date_.day + 1)
            except ValueError:
                year, month, day = (
                    (date_.year + 1, 1, 1)
                    if (date_.month + 1) > 12
                    else (date_.year, date_.month + 1, 1)
                )
                date_ = date_.replace(year, month, day)

    return True
