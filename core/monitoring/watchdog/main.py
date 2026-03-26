import json
import time
import traceback
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger

from ... import Config, ProcsDictTyping, ShmType, StatusCodes
from . import actions as act


class WatchDog:
    def __init__(
        self,
        sc: dict,
        procs: dict[int, ProcsDictTyping],
        id_info: dict[int, dict[int, str]],
        shm_s: dict[str, ShmType],
        sem_s: list[Semaphore],
        general_event: Event,
        sleep_logic: Event,
        warn_error_status: Semaphore,
    ) -> None:
        # initialization
        self.procs = procs  # Process's: Name, Func, ProcData, ID
        self.shms = shm_s  # ShM's & Memoryview[int]
        self.shm_buf = self.shms[Config.CoreConfig.Status.__name__]["buf"]
        # Semaphore's, Event
        self.all_sleep = general_event
        self.sleep_logic = sleep_logic
        self.calling = warn_error_status
        self.sems = sem_s
        # Variable's
        self._task: int = 0
        self._id_proc = 0
        self._check_proce_state: bool = False
        # StatusCodes
        self.sc: dict = sc  # Status Codes
        self.id_info = id_info
        self.general_sc = StatusCodes.general_sc
        self.warn: dict = self.sc["WARN"]
        self.error: dict = self.sc["ERROR"]

    @staticmethod
    def create(
        procs: dict[int, ProcsDictTyping],
        id_info: dict[int, dict[int, str]],
        shm_s: dict[str, ShmType],
        sem_s: list[Semaphore],
        general_event: Event,
        sleep_logic: Event,
        warn_error_status: Semaphore,
        file_path: str,
    ) -> object | None:
        try:
            with open(file_path, "rb") as f:
                status_codes = json.load(f)

            return WatchDog(
                sc=status_codes,
                procs=procs,
                id_info=id_info,
                shm_s=shm_s,
                sem_s=sem_s,
                general_event=general_event,
                sleep_logic=sleep_logic,
                warn_error_status=warn_error_status,
            )

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"WatchDog | GetStatusDict | {e}")
            return None

    def run_watchdog_engine(self) -> bool:
        # LocalLinks
        calling, shm_buf = self.calling, self.shm_buf
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
                        if task_action(sc_code=self._task, shm_buf=shm_buf) is False:
                            return False

                calling.acquire(timeout=60)

                # Check Status Module's
                for id_p in id_info.keys():  # Get ID Proc
                    for id_m in id_info[id_p]:  # Get ID Modules
                        sc_code = shm_buf[id_m]  # Get Status Code Module
                        if 50 <= sc_code < 256:  # Warn & Error Range
                            logger.warning(  # Logging Code Designaton
                                f"{id_info[id_p][id_m]} | {
                                    (warn if str(sc_code) in warn else error)[
                                        str(sc_code)
                                    ][str(id_m)]
                                }"
                            )
                            if (
                                task_action(
                                    sc_code=sc_code,
                                    shm_buf=shm_buf,
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
        shm_buf: memoryview,
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
                act.set_status_for_all_proc(  # All Sleep
                    shm_buf=shm_buf, procs=self.procs, stoping=True
                )
                act.sleep_untill_market_open(self.all_sleep)
                act.set_status_for_all_proc(  # All WeckUp
                    shm_buf=shm_buf, procs=self.procs, stoping=False
                )
                act.shms_zeros(self.shms)
                act.sems_clear(self.sems)
                self.sleep_logic.clear()
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
                shm_buf[id_m] = 0

            return True

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"WatchDog | TaskAction | {e}")
            return False
