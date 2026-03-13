import gc
import json
import traceback
from datetime import datetime, timedelta, timezone
from multiprocessing.synchronize import Semaphore

from loguru import logger


class WatchDog:
    def __init__(
        self,
        sc: dict,
        status_buf: memoryview,
        warn_error_status: Semaphore,
    ):
        # initializarion
        self.sc: dict = sc
        self.status_buf = status_buf
        self.warn_error_status = warn_error_status

        # StatusCodes init
        self.proc_name: dict[str, str] = self.sc["PROC_NAME"]
        self.id_info: dict[str, dict[str, dict[str, str]]] = self.sc["ID_INFO"]
        self.warn = self.sc["WARN"]
        self.error = self.sc["ERROR"]

    @staticmethod
    def create(
        status_buf: memoryview,
        warn_error_status: Semaphore,
        file_path: str,
    ):
        try:
            with open(file_path, "rb") as f:
                status_codes = json.load(f)

            return WatchDog(
                sc=status_codes,
                status_buf=status_buf,
                warn_error_status=warn_error_status,
            )

        except Exception as e:
            traceback.print_exc()
            logger.error(f"WatchDog | GetStatusDict | {e}")
            return None

    def _error_action(
        self,
        _int_code: int,
        _int_id_p: int,
    ):
        try:
            if 150 <= _int_code <= 255:
                return _int_id_p + 100

        except Exception as e:
            traceback.print_exc()
            logger.error(f"WatchDog | ErrorAction | {e}")
            return False

    def _set_status_for_all_proc(
        self,
        sbuf: memoryview,
        proc_name_: dict,
        stoping=True,
    ):
        if stoping:
            status_for_all_procs_ = 2
        else:
            status_for_all_procs_ = 1

        for id_p_ in proc_name_.keys():
            sbuf[int(id_p_)] = status_for_all_procs_
            logger.warning(
                f"{proc_name_[id_p_]} | {self.sc['GENERAL'][str(status_for_all_procs_)]}"
            )

    def _sleep_untill_market_open(
        self,
        _warn_error_status_: Semaphore,
    ):
        try:
            now = datetime.now(timezone.utc)
            tomorrow = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            sleep_time = (tomorrow - now).total_seconds()
            gc.collect()
            logger.debug("sleep")
            _warn_error_status_.acquire(timeout=sleep_time)

        except Exception as e:
            traceback.print_exc()
            logger.error(f"WatchDog | SleepUntillMarketOpen | {e}")
            return False

    def _warn_action(
        self,
        warn_error_status_: Semaphore,
        sbuf_: memoryview,
        proc_name_: dict,
        _int_code: int,
    ):
        try:
            if 100 <= _int_code < 150:
                self._set_status_for_all_proc(sbuf_, proc_name_, stoping=True)

                if self._sleep_untill_market_open(warn_error_status_) is False:
                    return False

                self._set_status_for_all_proc(sbuf_, proc_name_, stoping=False)
                return 201

            else:
                return None

        except Exception as e:
            traceback.print_exc()
            logger.error(f"WatchDog | WarnAction | {e}")
            return False

    def _check_status_modules(
        self,
        warn_error_status_: Semaphore,
        sbuf_: memoryview,
        id_info_: dict,
        warn_: dict,
        error_: dict,
        proc_name_: dict,
    ):
        warn_action_, error_action_ = self._warn_action, self._error_action
        try:
            for id_p_ in id_info_.keys():
                for id_m_ in id_info_[id_p_]:
                    _int_code = sbuf_[int(id_m_)]
                    _str_code, _int_id_p, _int_id_m = (
                        str(_int_code),
                        int(id_p_),
                        int(id_m_),
                    )

                    if _str_code in warn_:
                        logger.warning(
                            f"{id_info_[id_p_][id_m_]['name']} | {warn_[_str_code][id_m_]}"
                        )
                        if (
                            task := warn_action_(
                                warn_error_status_,
                                sbuf_,
                                proc_name_,
                                _int_code,
                            )
                        ) is not False:
                            return task

                        else:
                            return False

                    elif _str_code in error_:
                        logger.error(
                            f"{id_info_[id_p_][id_m_]['name']} | {error_[_str_code][id_m_]}"
                        )
                        if (
                            task := error_action_(
                                _int_code,
                                _int_id_p,
                            )
                            is not False
                        ):
                            return task
                        else:
                            return False
                    else:
                        continue

        except Exception as e:
            traceback.print_exc()
            logger.error(f"WatchDog | CheckStatusModules | {e}")
            return False

    def run_watchdog_engine(
        self,
    ):
        # Semaphore, Event - LocalLinks
        _warn_error_status = self.warn_error_status
        # Shm.Buf - LocalLinks
        _status_buf = self.status_buf
        # StatusCodeDicts - LocalLinks
        _proc_name, _error, _warn, _id_info, _sc = (
            self.proc_name,
            self.error,
            self.warn,
            self.id_info,
            self.sc,
        )
        # Other - LocalLinks
        _check_status_modules_ = self._check_status_modules
        _counter = 0
        #  - - -
        logger.info("WatchDog | Started")
        while True:
            try:
                if (
                    task := _check_status_modules_(
                        _warn_error_status,
                        _status_buf,
                        _id_info,
                        _warn,
                        _error,
                        _proc_name,
                    )
                ) is not False:
                    if isinstance(task, int):
                        return task

                    elif task:
                        continue

                    else:
                        if _warn_error_status.get_value() == 0:
                            _counter += 1

                        _warn_error_status.acquire(timeout=60)
                        if _counter >= 3:
                            return 0
                else:
                    return False

            except Exception as e:
                traceback.print_exc()
                logger.error(f"WatchDog | RunStatusAgent | {e}")
                return False
