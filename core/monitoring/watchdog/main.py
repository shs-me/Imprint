import time
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger

from ... import Config, IDpm, ProcsDictTyping, ShMs
from ... import StatusCodes as sc
from . import actions as act


class WatchDog:
    def __init__(
        self,
        procs: dict[int, ProcsDictTyping],
        id_info: dict[IDpm, dict[IDpm, str]],
        shm_buf: memoryview,
        general_event: Event,
        sc_sem: Semaphore,
    ) -> None:
        self.procs, self.buf = procs, shm_buf
        self.status_buf = self.buf[slice(*ShMs.status_offset)]
        self.error_id = Config.CoreConfig.Status.id_error
        self.sleep_all, self.sc_sem = general_event, sc_sem
        # Variable's
        self._task, self._id_proc = 0, 0
        self._check_proce_state: bool = False
        # StatusCodes
        self.id_info = id_info

    def run_watchdog_engine(self) -> bool:
        # LocalLinks
        sc_sem, shm_buf = self.sc_sem, self.status_buf
        id_info = self.id_info
        task_action = self._task_action
        err_id = self.error_id
        #  - - -
        self.sleep_all.clear()
        counter = 0
        while True:
            if sc_sem.get_value() == 0:
                counter += 1
                if counter >= 3:
                    self._task = 1  # Check Live: Not Reason
                    if task_action(sc_code=self._task) is False:
                        return False

            sc_sem.acquire(timeout=60)

            # Check Status Module's
            if shm_buf[err_id] == sc.ERROR:
                logger.error(f"WatchDog | {sc.ERROR.get_msg()}")
                return False

            for id_p in id_info.keys():  # Get ID Proc
                for id_m in id_info[id_p]:  # Get ID Modules
                    sc_code = shm_buf[id_m]  # Get Status Code Module
                    if sc.ERR_RE <= sc_code < 255:  # Warn & Error Range
                        msg = sc(sc_code).get_msg(id_m)
                        logger.warning(f"{id_info[id_p][id_m]} | {msg}")
                        if (
                            task_action(
                                sc_code=sc_code,
                                id_m=id_m,
                                id_p=id_p,
                            )
                            is False
                        ):
                            return False

    def _task_action(
        self,
        sc_code: int,
        id_m: int | None = None,
        id_p: int | None = None,
    ) -> bool:
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
            act.sleep_untill_market_open(self.sleep_all)
            act.set_status_for_procs(  # All WeckUp
                status_buf=self.status_buf, procs=self.procs, stoping=False
            )
            act.reset(self.buf)
            self.sleep_all.set()
            time.sleep(0.5)
            self.sleep_all.clear()

        elif task == 150 or task == 50 or task == 51:
            if id_p:  # Check Proc Live or Died
                if act.check_proc(id_proc=id_p, procs_info=self.procs) is False:
                    return False

        # Reset Status
        self._task = 0
        if id_m:
            self.status_buf[id_m] = 0

        return True
