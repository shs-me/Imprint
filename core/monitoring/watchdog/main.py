import time
import traceback
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger

from core.settings import IDpm

from ... import ProcsDictTyping, ShMs, StatusCodes
from . import actions as act


class WatchDog:
    def __init__(
        self,
        procs: dict[int, ProcsDictTyping],
        id_info: dict[IDpm, dict[IDpm, str]],
        shm_buf: memoryview,
        sem_s: list[Semaphore],
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> None:
        self.procs, self.buf, self.sem_s = procs, shm_buf, sem_s
        self.status_buf = self.buf[slice(*ShMs.status_offset)]
        self.all_sleep, self.calling = general_event, warn_error_status
        # Variable's
        self._task, self._id_proc = 0, 0
        self._check_proce_state: bool = False
        # StatusCodes
        self.id_info = id_info
        self.warn, self.error = StatusCodes.WARN, StatusCodes.ERROR

    def run_watchdog_engine(self) -> bool:
        # LocalLinks
        calling, shm_buf = self.calling, self.status_buf
        error, warn, id_info = self.error, self.warn, self.id_info
        task_action = self._task_action
        #  - - -
        self.all_sleep.clear()
        counter = 0
        while True:
            try:
                if calling.get_value() == 0:
                    counter += 1
                    if counter >= 3:
                        self._task = 1  # Check Live: Not Reason
                        if task_action(sc_code=self._task) is False:
                            return False

                calling.acquire(timeout=60)

                # Check Status Module's
                for id_p in id_info.keys():  # Get ID Proc
                    for id_m in id_info[id_p]:  # Get ID Modules
                        sc_code = shm_buf[id_m]  # Get Status Code Module
                        if 50 <= sc_code < 256:  # Warn & Error Range
                            _, __, ___ = str(id_m), str(sc_code), id_info[id_p][id_m]
                            if __ in warn:
                                # msg = warn(sc_code).get_msg(id_m)
                                logger.warning(f"{___} | {warn[__][_]}")

                            elif __ in error:
                                # msg = error(sc_code).get_msg(id_m)
                                logger.error(f"{___} | {error[__][_]}")

                            if (
                                task_action(
                                    sc_code=sc_code,
                                    id_m=id_m,
                                    id_p=id_p,
                                )
                                is False
                            ):
                                return False

            except Exception as e:
                traceback.print_exc()  # Debug
                logger.error(f"WatchDog | RunStatusAgent | {e}")
                return False

    def _task_action(
        self,
        sc_code: int,
        id_m: int | None = None,
        id_p: int | None = None,
    ) -> bool:
        try:
            self._task = (
                task
                if isinstance(
                    (task := act.init_task(sc_code=sc_code, last_task=self._task)),
                    int,
                )
                else self._task
            )
            if task == 1:  # Check Procs Live's or Died's
                for id_proc in self.procs:
                    if act.check_proc(id_proc=id_proc, procs_info=self.procs) is False:
                        return False

            elif task == 101:  # Sleep All Procs untill market open
                act.set_status_for_procs(  # All Sleep
                    status_buf=self.status_buf, procs=self.procs, stoping=True
                )
                act.sleep_untill_market_open(self.all_sleep)
                act.set_status_for_procs(  # All WeckUp
                    status_buf=self.status_buf, procs=self.procs, stoping=False
                )
                act.reset(self.buf, self.sem_s)
                self.all_sleep.set()
                time.sleep(0.5)
                self.all_sleep.clear()

            elif task == 150 or task == 50 or task == 51:
                if id_p:  # Check Proc Live or Died
                    if act.check_proc(id_proc=id_p, procs_info=self.procs) is False:
                        return False

            # Reset Status
            self._task = 0
            if id_m:
                self.status_buf[id_m] = 0

            return True

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"WatchDog | TaskAction | {e}")
            return False
