from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from loguru import logger

from ... import configurations as cfg
from . import StatusCodes as sc
from . import actions as act


class MainManager:
    def __init__(
        self,
        segments: dict[str, Any],
        configs: dict[str, Any],
        shm_buf: memoryview,
    ) -> None:
        self.shm_buf = shm_buf
        self.segments_init(segments)
        self.configs_init(configs)
        self.local_segments_init()

    def segments_init(self, segments: dict[str, Any]) -> None:
        _slice: slice
        segments_subclasses: list[str] = segments["subclasses"]
        for name, _slice in segments.items():
            if isinstance(_slice, list):
                continue

            if name not in segments_subclasses:
                raise ValueError(
                    f"{name} not subclass {cfg.ConfigurationSHMSegments.__name__}"
                )

            if name == cfg.ConfigurationMonitoring.__name__:
                self.monitoring_buf = self.shm_buf[_slice]

    def configs_init(self, configs: dict[str, Any]) -> None:
        config_subclasses: list[str] = configs["subclasses"]
        for name, obj in configs.items():
            if isinstance(obj, list):
                continue

            if name not in config_subclasses:
                raise ValueError(f"{name} not subclass {cfg.Configuration.__name__}")

            if isinstance(obj, cfg.ConfigurationMonitoring):
                self.cfgMonitoring = obj

    def local_segments_init(self) -> None:
        self.status_buf = self.monitoring_buf[slice(*self.cfgMonitoring.status)]
        self.id_err = self.cfgMonitoring.id_error

    def run(
        self,
        procs: dict[int, dict],
        general_event: Event,
        sc_sem: Semaphore,
    ) -> bool:
        self.procs = _procs = procs
        self.sc_sem = _sc_sem = sc_sem
        self.sleep_all = _sleep_all = general_event
        # LocalLinks
        status_buf = self.status_buf
        error_check, warn_check = self._error_check, self._warn_check
        check_procs = self._check_procs
        #  - - -
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
        if status_buf[self.id_err] == sc.ERROR:
            logger.error(f"MainManager | {sc.ERROR.get_msg()}")
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
        if sc.WARN0 <= sc_code <= sc.WARN4:
            self.sleep_all.clear()
            act.set_status_for_procs(  # All Sleep
                status_buf=self.status_buf, procs=procs, stoping=True
            )
            act.sleep_untill_market_open(self.sleep_all)
            act.set_status_for_procs(  # All WeckUp
                status_buf=self.status_buf, procs=procs, stoping=False
            )
            act.reset(self.shm_buf)
            self.sleep_all.set()

        return True
