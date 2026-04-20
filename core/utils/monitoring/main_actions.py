from datetime import datetime, timedelta, timezone
from multiprocessing.synchronize import Event

from loguru import logger

from . import StatusCodes as sc


def data_preppered(procs: dict, proc_id: int, status_buf: memoryview):
    for id_p, data in procs.items():
        status_buf[data["task_id"]] = sc.COMPLETE

    procs.pop(proc_id)


def set_status_for_procs(
    status_buf: memoryview, procs: dict[int, dict], stoping=True
) -> None:
    sc_code = sc.STOP if stoping else sc.RUN
    for id_p, data in procs.items():
        status_buf[id_p] = sc_code
        logger.success(f"{data['proc_name']} | {sc(sc_code).name}")


def sleep_untill_market_open(sleep_all: Event) -> None:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    sleep_time = (tomorrow - now).total_seconds()
    sleep_all.wait(timeout=sleep_time)


def reset(buf: memoryview) -> None:
    buf[:] = b"\x00" * len(buf)


def check_proc(id_proc: int, procs: dict[int, dict]) -> bool:
    data = procs[id_proc]
    if data["proc"].is_alive() is False:
        logger.warning(
            f"MainManager | CheckProc | Process {data['proc_name']} is dead."
        )
        return False

    else:
        return True
