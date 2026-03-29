from datetime import datetime, timedelta, timezone
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger

from ... import ProcsDictTyping, ShmType


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


def set_status_for_all_proc(shm_buf: memoryview, procs: dict, stoping=True) -> None:
    if stoping:
        sc_code_for_all_procs = 2
    else:
        sc_code_for_all_procs = 1

    for id_p, data in procs.items():
        shm_buf[id_p] = sc_code_for_all_procs


def sleep_untill_market_open(all_sleep: Event) -> None:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    sleep_time = (tomorrow - now).total_seconds()
    all_sleep.wait(timeout=sleep_time)


def shms_zeros(shms: dict[str, ShmType]) -> None:
    for name in shms.keys():
        shms[name]["buf"][:] = b"\x00" * shms[name]["shm"].size


def sems_clear(sems: list[Semaphore]) -> None:
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
