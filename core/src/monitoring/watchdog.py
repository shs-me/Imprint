import gc
import json
import time
import traceback
from datetime import datetime, timedelta, timezone
from multiprocessing.synchronize import Event, Semaphore

from loguru import logger


class WatchDog:
    def __init__(
        self,
        sc: dict,
        procs: dict,
        shm_s: dict,
        sem_s: list,
        general_event: Event,
        warn_error_status: Semaphore,
    ):
        # initializarion
        self._procs = procs  # Process's: Name, Func, ProcData, ID
        # SharedMemory's
        self._shms: dict = shm_s
        self.status_buf = self._shms["status"]["buf"]
        # Semaphore's, Event
        self.general_event: Event = general_event
        self.warn_error_status = warn_error_status
        self.sem_s = sem_s
        # Variable's
        self._task: int = 0
        self._id_proc = 0
        self._check_proce_state: bool = False
        # StatusCodes
        self.sc: dict = sc  # Status Codes
        self.warn: dict = self.sc["WARN"]
        self.error: dict = self.sc["ERROR"]
        self.procs_name: dict[str, str] = self.sc["PROC_NAME"]
        self.id_info: dict[str, dict[str, dict[str, str]]] = self.sc["ID_INFO"]

    @staticmethod
    def create(
        procs: dict,
        shm_s: dict,
        sem_s: list,
        general_event: Event,
        warn_error_status: Semaphore,
        file_path: str,
    ) -> object | None:
        try:
            with open(file_path, "rb") as f:
                status_codes = json.load(f)

            return WatchDog(
                sc=status_codes,
                procs=procs,
                shm_s=shm_s,
                sem_s=sem_s,
                general_event=general_event,
                warn_error_status=warn_error_status,
            )

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"WatchDog | GetStatusDict | {e}")
            return None

    # Start
    def run_watchdog_engine(
        self,
    ) -> bool:
        # StatusCodeDicts - LocalLinks
        _procs_name, _error, _warn, _id_info, _sc = (
            self.procs_name,
            self.error,
            self.warn,
            self.id_info,
            self.sc,
        )
        # Semaphore, Event - LocalLinks
        _warn_error_status, _general_event = self.warn_error_status, self.general_event
        # Shm.Buf - LocalLinks
        _status_buf = self.status_buf
        # Other - LocalLinks
        _task_action, _init_task = self._task_action, self._init_task
        _counter = 0
        #  - - -
        self.general_event.clear()
        while True:
            try:
                # if self._check_proce_state:  # Checker Active?
                # if self._check_proc(self._id_proc) is False:
                #   return False

                if _warn_error_status.get_value() == 0:
                    _counter += 1
                    if _counter >= 3:
                        self._task = 1  # Check Live: Not Reason
                        if (
                            _task_action(
                                _code=1,
                                general_event=_general_event,
                                status_buf=_status_buf,
                                procs_name=_procs_name,
                                init_task_=_init_task,
                            )
                            is False
                        ):
                            return False

                _warn_error_status.acquire(timeout=60)

                # Check Status module's
                for id_p_ in _id_info.keys():  # Get ID Proc, str
                    for id_m_ in _id_info[id_p_]:  # Get ID Modules on ID proc, str
                        _code = _status_buf[int(id_m_)]  # Get Status Code Module, int
                        # Convert's
                        _str_code, _int_id_p, _int_id_m = (
                            str(_code),
                            int(id_p_),
                            int(id_m_),
                        )
                        # Warn & Error Range
                        if 50 <= _code < 256:
                            # Logging Code Designaton
                            if _str_code in _warn:
                                logger.warning(
                                    f"{_id_info[id_p_][id_m_]['name']} | {_warn[_str_code][id_m_]}"
                                )

                            if _str_code in _error:
                                logger.error(
                                    f"{_id_info[id_p_][id_m_]['name']} | {_error[_str_code][id_m_]}"
                                )
                            # Action's id False Close Core
                            if (
                                _task_action(
                                    _code=_code,
                                    general_event=_general_event,
                                    status_buf=_status_buf,
                                    procs_name=_procs_name,
                                    init_task_=_init_task,
                                    _id_m=_int_id_m,
                                    _id_p=_int_id_p,
                                )
                                is False
                            ):
                                return False

            except Exception as e:
                traceback.print_exc()  # Debug
                logger.error(f"WatchDog | RunStatusAgent | {e}")
                return False

    # Shm's Zeros
    def _shm_zeros(
        self,
    ) -> bool:
        try:
            for name in self._shms.keys():
                self._shms[name]["buf"][:] = b"\x00" * self._shms[name]["shm"].size

            return True

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"WatchDog | ShmZeros | {e}")
            return False

    # Sem's clear
    def _sems_clear(
        self,
    ) -> None:
        for sem in self.sem_s:
            while sem.acquire(block=False):
                pass

    # Check Process
    def _check_proc(
        self,
        id_proc: int,
    ) -> bool:
        try:
            if self._procs[id_proc]["proc"].is_alive() is not True:
                if self._check_proce_state is True:
                    logger.warning(
                        f"WatchDog | CheckProc | Failed to run {self._procs[id_proc]['name']} Process."
                    )
                    return False

                else:
                    logger.warning(
                        f"WatchDog | CheckProc | Process {self._procs[id_proc]['name']} is dead. Restarting..."
                    )
                    return False
                    #  - - -
                    self._check_proce_state = True
                    self._id_proc = id_proc

            else:
                self._check_proce_state = False
                return True

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"Watchdog | CheckProc | {e}")
            return False

    # Action's
    def _task_action(
        self,
        _code: int,
        general_event: Event,
        status_buf: memoryview,
        procs_name: dict,
        init_task_,
        _id_m: int | None = None,
        _id_p: int | None = None,
    ) -> bool:
        try:
            self._task = (
                task if isinstance((task := init_task_(_code)), int) else self._task
            )
            # Check Procs Live or not
            if task == 1:
                for id_proc in self._procs:
                    if self._check_proc(id_proc=id_proc) is False:
                        return False

            # Sleep All Procs untill market open
            elif task == 101:
                # Sleep
                self._set_status_for_all_proc(status_buf, procs_name, stoping=True)
                self._sleep_untill_market_open(general_event)
                # Start
                self._set_status_for_all_proc(status_buf, procs_name, stoping=False)

                if self._shm_zeros() is True:
                    for id_proc in self._procs:
                        if self._check_proc(id_proc=id_proc) is False:
                            return False

                    self._sems_clear()
                    self.general_event.set()
                    time.sleep(0.1)
                    self.general_event.clear()

                else:
                    return False

            # Check Proc live or not
            elif task == 150 or task == 50 or task == 51:
                if _id_p:
                    if self._check_proc(id_proc=_id_p) is False:
                        return False

            # Reset Status
            self._task = 0
            if _id_m:
                status_buf[_id_m] = 0
                print(_id_m)
            return True

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"WatchDog | TaskAction | {e}")
            return False

    def _init_task(
        self,
        _code: int,
    ) -> int | None:
        if self._task == 0:  # Task Active?
            if _code < 150:  # Warn's
                if _code < 100:  # ProfilingTask
                    # - - -
                    return 50  # Check Proc

                elif _code < 150:  # Bot Task's
                    # - - -
                    return 101  # Sleep untill market open

            if _code < 256:  # Error's
                #  - - -
                return 150  # Check Proc
        else:
            return None  # Active Task

    def _set_status_for_all_proc(
        self,
        status_buf: memoryview,
        proc_name_: dict,
        stoping=True,
    ) -> None:
        if stoping:
            status_for_all_procs_ = 2
        else:
            status_for_all_procs_ = 1

        for id_p_ in proc_name_.keys():
            status_buf[int(id_p_)] = status_for_all_procs_
            logger.warning(
                f"{proc_name_[id_p_]} | {self.sc['GENERAL'][str(status_for_all_procs_)]}"
            )

    def _sleep_untill_market_open(
        self,
        _general_event: Event,
    ) -> None:
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        sleep_time = (tomorrow - now).total_seconds()
        gc.collect()
        _general_event.wait(timeout=sleep_time)
