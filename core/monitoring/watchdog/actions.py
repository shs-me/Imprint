from datetime import datetime, timedelta, timezone
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger

from ... import ProcsDictTyping, StatusCodes


def init_task(sc_code: int, last_task: int) -> int | None:
    if last_task == 0:  # Task Active? True No
        if sc_code < 150:  # Warn's
            if sc_code < 100:  # ProfilingTask
                # - - -
                return 50  # Check Proc

            elif sc_code < 150:  # Bot Task's
                # - - -
                return 101  # Sleep untill market open

        if sc_code < 256:  # Error's
            #  - - -
            return 150  # Check Proc
    else:
        return None  # Active Task


def set_status_for_procs(
    status_buf: memoryview, procs: dict[int, ProcsDictTyping], stoping=True
) -> None:
    sc_code = 2 if stoping else 1
    for id_p, data in procs.items():
        status_buf[id_p] = sc_code
        logger.success(f"{data['name']} | {StatusCodes.General(sc_code).name}")


def sleep_untill_market_open(all_sleep: Event) -> None:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    sleep_time = (tomorrow - now).total_seconds()
    all_sleep.wait(timeout=sleep_time)


def reset(buf: memoryview, sems: list[Semaphore]) -> None:
    buf[:] = b"\x00" * len(buf)
    for sem in sems:
        while sem.acquire(block=False):
            pass


def check_proc(id_proc: int, procs_info: dict[int, ProcsDictTyping]) -> bool:
    _data = procs_info[id_proc]
    if _data["proc"] is not None:
        if _data["proc"].is_alive() is False:
            logger.warning(f"WatchDog | CheckProc | Process {_data['name']} is dead.")
            return False

        else:
            return True
    else:
        return False
