import time
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger

from ... import Config, ShmBufOffset
from ... import StatusCodes as sc
from . import actions as act


class WatchDog:
    def __init__(
        self,
        procs: dict[int, dict],
        shm_buf: memoryview,
        general_event: Event,
        sc_sem: Semaphore,
    ) -> None:
        __cfg = Config.ShmSharing
        self.procs, self.buf = procs, shm_buf
        self.monitoring_buf = self.buf[slice(*ShmBufOffset.monitoring)]
        self.status_buf = self.monitoring_buf[slice(*__cfg.Monitoring.status)]
        self.error_id: int = __cfg.Monitoring.id_error
        self.sleep_all, self.sc_sem = general_event, sc_sem

    def run_watchdog_engine(self) -> bool:
        # LocalLinks
        procs, sc_sem, status_buf = self.procs, self.sc_sem, self.status_buf
        error_check, warn_check = self._error_check, self._warn_check
        check_procs = self._check_procs
        #  - - -
        self.sleep_all.clear()
        while True:
            sc_sem.acquire(timeout=60)
            if error_check(status_buf) is not False:
                if warn_check(status_buf, procs) is not False:
                    if check_procs(procs) is not False:
                        continue

                    return False
                return False
            return False

    def _check_procs(self, procs):
        for id_proc in procs.keys():
            if act.check_proc(id_proc=id_proc, procs=procs) is False:
                return False

    def _error_check(self, status_buf: memoryview):
        if status_buf[self.error_id] == sc.ERROR:
            logger.error(f"WatchDog | {sc.ERROR.get_msg()}")
            return False

    def _warn_check(self, status_buf: memoryview, procs: dict[int, dict]):
        for id_p, data in procs.items():
            sc_code = status_buf[id_p]
            if sc.WARN_RE < sc_code < 255:
                msg = sc(sc_code).get_msg(data["proc_name"])
                logger.warning(f"{data['proc_name']} | {msg}")
                if self._task_action(sc_code, procs) is False:
                    return False

    def _task_action(
        self,
        sc_code: int,
        procs: dict,
    ) -> bool:
        if sc.WARN0 <= sc_code <= sc.WARN1:
            act.set_status_for_procs(  # All Sleep
                status_buf=self.status_buf, procs=procs, stoping=True
            )
            act.sleep_untill_market_open(self.sleep_all)
            act.set_status_for_procs(  # All WeckUp
                status_buf=self.status_buf, procs=procs, stoping=False
            )
            act.reset(self.buf)
            self.sleep_all.set()
            time.sleep(0.5)
            self.sleep_all.clear()

        return True
