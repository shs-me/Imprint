import time
import traceback
from multiprocessing.synchronize import Semaphore

import numpy as np

from .. import Config, ShMs, StatusCodes


class MonitorObj:
    def __init__(
        self,
        shm_buf: memoryview,
        proc_name: str,
        warn_error_status: Semaphore,
        monitor: Semaphore,
    ):
        self.__cfg, self.proc_name, self.shm_buf = Config.CoreConfig, proc_name, shm_buf
        self.lines, self.cols = self.__cfg.Profiling.lines, self.__cfg.Profiling.cols
        self._warn_error_status, self._monitor = warn_error_status, monitor
        self._init_session()
        _obj = getattr(self.__cfg.Status, proc_name)
        self.id_p, self.id_m = _obj.id_p, _obj.id_m
        self.id_d, self.dgc = _obj.id_d, _obj.id_dgc
        self.profiling_buf[(64 + self.dgc)] = self.id_m
        self.headers_buf = self.profiling_buf[(self.dgc * 8) : (self.dgc * 8 + 8)].cast(
            "I"
        )
        # Get Index LineID from HeadersBuf[ProfilingShM.Buf]
        self.dgid: int = self.headers_buf[0]

    def _init_session(self) -> None:
        scg = StatusCodes.General
        self.INFO_RANGE = Config.general_sc[1]
        self.STOPING, self.SLEEP, self.WAKE_UP = scg.STOPING, scg.SLEEP, scg.WAKE_UP

        self.raw_buf = self.shm_buf[slice(*ShMs.raw_offset)]
        self.grid_buf = self.shm_buf[slice(*ShMs.grid_offset)]
        self.metrics_buf = self.shm_buf[slice(*ShMs.metrics_offset)]
        self.status_buf = self.shm_buf[slice(*ShMs.status_offset)]
        self.profiling_buf = self.shm_buf[slice(*ShMs.profiling_offset)]

        self.dgarray = np.ndarray(
            (self.lines, self.cols),
            dtype=np.int64,
            buffer=self.profiling_buf[self.__cfg.Profiling.offset :],
        )

    def set_status(self, id_m: int, code: int) -> bool:
        """
        IF code > 49: set code on StatusShM.buf[ID_M].\n
        Else, called func "_profiling_" that set code+time_ns on ProfilingShM.\n
        """
        try:
            if code > self.INFO_RANGE:
                self.status_buf[id_m] = code
                self._warn_error_status.release()
            else:
                self._profiling_(code)

            return True

        except Exception as e:
            traceback.print_exc()  # Debug
            raise Exception(e)

    def _profiling_(self, code: int) -> None:
        """
        Set TimeNS on 2-D Array, Buffer: Profiling ShM.\n
        Also set IndexLine & StatusCode on Headers Profiling ShM.
        """
        dgid_m = self.dgid
        # - - -
        self.dgarray[dgid_m, self.dgc] = time.time_ns()
        self.headers_buf[0], self.headers_buf[1] = dgid_m, code
        self.dgid = (dgid_m + 1) % self.lines
        self._monitor.release()

    def have_problem(self) -> bool | None:
        """
        Get StatusCode Module. IF status_code == Warn|Error: return True. Else: return False
        """
        try:
            if self.status_buf[self.id_m] > self.INFO_RANGE:
                return True

            elif self.status_buf[self.id_d] > self.INFO_RANGE:
                return True

            return False

        except Exception as e:
            traceback.print_exc()  # Debug
            raise Exception(e)

    def have_watchdog_task(self) -> bool:
        if self.status_buf[self.id_p] == self.STOPING:
            return True

        return False

    @staticmethod
    def dump_profile(file_path: str, _X_: np.ndarray | memoryview, _bin=False) -> None:
        """Save ShMemory/NDarray to .bin/.csv"""
        try:
            if _bin:
                with open(file_path, "wb") as f:
                    f.write(_X_[:])
            else:
                if isinstance(_X_, np.ndarray):
                    np.savetxt(
                        file_path,
                        _X_,
                        fmt="%d",
                        delimiter=",",
                    )

        except Exception as e:
            traceback.print_exc()  # Debug
            raise Exception(e)
