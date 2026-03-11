import gc
import json
import sys
from datetime import datetime, timedelta, timezone
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event, Semaphore
from typing import TypedDict

from loguru import logger

STATUS = {
    "shm": None,
    "buf": None,
}


class ShmType(TypedDict):
    shm: SharedMemory
    buf: memoryview


class HealthCheck:
    def __init__(
        self,
        sc: dict,
        cfg,
        sem_sleep_main,
        warn_error_status,
    ):
        # initializarion
        self.sc: dict = sc
        self.cfg: dict = cfg
        self.sem_sleep_main: Semaphore = sem_sleep_main
        self.warn_error_status: Event = warn_error_status

        # SharedMemory init
        self._status: ShmType = STATUS  # type: ignore
        # Index process monitoring for statusCode
        self.id_pm = self.cfg["status"]["monitoring"]
        if self._shm_control() is False:
            sys.exit()

        # StatusCodes init
        self._proc_name: dict[str, str] = self.sc["PROC_NAME"]
        self._id_info: dict[str, dict[str, dict[str, str]]] = self.sc["ID_INFO"]
        self._warn = self.sc["WARN"]
        self._error = self.sc["ERROR"]

    @staticmethod
    def create(
        **argg,
    ):
        try:
            with open(argg["file_path"], "rb") as f:
                status_codes = json.load(f)

            return HealthCheck(
                sc=status_codes,
                cfg=argg["cfg"],
                sem_sleep_main=argg["sem_sleep_main"],
                warn_error_status=argg["warn_error_status"],
            )

        except Exception as e:
            logger.error(f"HealthCheck | GetStatusDict | {e}")
            return None

    def _shm_control(
        self,
    ):  # Load SharedMemory-s
        try:
            shm = SharedMemory(
                name=self.cfg["status"]["shm"],
            )
            if isinstance(shm.buf, memoryview):
                self._status["shm"], self._status["buf"] = shm, shm.buf

        except Exception as e:
            logger.error(f"HealthCheck | ShmControl | {e}")
            self.sem_sleep_main.release()
            return False

    def _set_status(
        self,
        code,
    ):
        self._status["buf"][self.id_pm] = code
        self.sem_sleep_main.release()

    def _set_status_for_all_proc(
        self,
        stoping=True,
    ):
        if stoping:
            _status_for_all_procs = 2
        else:
            _status_for_all_procs = 1

        _procs = self._proc_name
        for _id_p in _procs.keys():
            self._status["buf"][int(_id_p)] = _status_for_all_procs
            logger.warning(
                f"{_procs[_id_p]} | {self.sc['GENERAL'][str(_status_for_all_procs)]}"
            )

    def _sleep_untill_market_open(
        self,
    ):
        try:
            now = datetime.now(timezone.utc)
            tomorrow = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            sleep_time = (tomorrow - now).total_seconds()
            gc.collect()
            self.warn_error_status.wait(timeout=sleep_time)

        except Exception as e:
            logger.error(f"HealthCheck | SleepUntillMarketOpen | {e}")
            return False

    def _error_action(
        self,
        _int_code: int,
        _int_id_p: int,
    ):
        try:
            if _int_code < 200:
                self._set_status(_int_id_p + 100)
                self.sem_sleep_main.release()

        except Exception as e:
            logger.error(f"HealthCheck | ErrorAction | {e}")
            return False

    def _warn_action(
        self,
        _int_code: int,
    ):
        try:
            if _int_code >= 100:
                self._set_status(200)  # SleepUntillMarketOpen
                self._set_status_for_all_proc(stoping=True)

                if self._sleep_untill_market_open() is False:
                    return False

                self._set_status_for_all_proc(stoping=True)
                self._set_status(201)  # WeckUpProcs

                self.sem_sleep_main.release()

        except Exception as e:
            logger.error(f"HealthCheck | WarnAction | {e}")
            return False

    def _check_status_modules(
        self,
    ):
        try:
            _id_info_, _warn_, _error_ = self._id_info, self._warn, self._error

            for _id_p in _id_info_.keys():
                for _id_m in _id_info_[_id_p]:
                    _int_code = self._status["buf"][int(_id_m)]
                    _str_code, _int_id_p, _int_id_m = (
                        str(_int_code),
                        int(_id_p),
                        int(_id_m),
                    )

                    if _str_code != _id_info_[_id_p][_id_m]["set_code"]:
                        _id_info_[_id_p][_id_m]["set_code"] = _str_code

                        if _str_code in self.sc["WARN"]:
                            logger.warning(
                                f"{_id_info_[_id_p][_id_m]['name']} | {_warn_[_str_code][_id_m]}"
                            )
                            if self._warn_action(_int_code) is False:
                                return False

                        elif _str_code in self.sc["ERROR"]:
                            logger.error(
                                f"{_id_info_[_id_p][_id_m]['name']} | {_error_[_str_code][_id_m]}"
                            )
                            if self._error_action(_int_code, _int_id_p) is False:
                                return False
                    else:
                        continue

        except Exception as e:
            logger.error(f"HealthCheck | CheckStatusModules | {e}")
            return False

    def run_health_check_engine(
        self,
    ):
        logger.info("HealthCheck | Started")
        while True:
            try:
                if self._status["buf"][self.id_pm] != 3:
                    self._set_status(4)  # IDLE
                    self.warn_error_status.wait()

                    self.warn_error_status.clear()

                    self._set_status(1)  # Running
                    if self._check_status_modules() is False:
                        self._set_status(3)

                else:
                    break

            except Exception as e:
                logger.error(f"HealthCheck | RunStatusAgent | {e}")
                self._set_status(3)
                break


def run_monitoring(
    config: dict,
    sem_sleep_main: Semaphore,
    warn_error_status: Event,
):
    logger.remove()

    logger.add(
        "logs/monitoring.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    gc.disable()
    agent = HealthCheck.create(
        cfg=config,
        sem_sleep_main=sem_sleep_main,
        warn_error_status=warn_error_status,
        file_path="status_codes.json",
    )
    if isinstance(agent, HealthCheck):
        agent.run_health_check_engine()
