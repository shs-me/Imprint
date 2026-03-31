import time
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Semaphore

import numpy as np

from .. import Config, ShMs, ShmType


class MonitorObj:
    def __init__(
        self,
        proc_name: str,
        warn_error_status: Semaphore,
        _monitor: Semaphore | None = None,
    ):
        self.__cfg = Config.CoreConfig
        self.lines, self.cols = self.__cfg.Profiling.lines, self.__cfg.Profiling.cols
        self.shms: dict[str, ShmType] = ShMs.shms
        self._warn_error_status: Semaphore = warn_error_status
        try:
            self._shm_init()
            self.status_buf = self.shms[self.__cfg.Status.__name__]["buf"]
            self.profiling_buf = self.shms[self.__cfg.Profiling.__name__]["buf"]
            if proc_name != Config.CoreConfig.Profiling.__name__:  # StatusSHM init
                if _monitor is not None:
                    self._monitor = _monitor

                _obj = getattr(self.__cfg.Status, proc_name)
                self.id_p, self.id_m = _obj.id_p, _obj.id_m
                self.id_d, self.dgc = _obj.id_d, _obj.id_dgc
                self._profiling_array_init()

                self.profiling_buf[(64 + self.dgc)] = self.id_m
                self.headers_buf = self.profiling_buf[
                    (self.dgc * 8) : (self.dgc * 8 + 8)
                ].cast("I")
                # Get Index LineID from HeadersBuf[ProfilingShM.Buf]
                self.dgid: int = self.headers_buf[0]

            else:
                self._profiling_array_init(headers=True)

        except Exception as e:
            traceback.print_exc()  # Debug
            raise Exception(e)

    def _shm_init(self) -> None | Exception:
        """Load SharedMemory-s, IF SHM not found, raise FileNotFoundError"""
        try:
            for name in self.shms.keys():
                _obj = getattr(self.__cfg, name)
                shm = SharedMemory(name=_obj.shm_name)
                if shm.buf is not None:
                    self.shms[name]["shm"] = shm
                    self.shms[name]["buf"] = shm.buf

        except FileNotFoundError as e:
            traceback.print_exc()  # Debug
            raise FileNotFoundError(e)

    def _profiling_array_init(self, headers=False) -> None:
        """
        Create 2-D Array on buffer: ProfilingShM.\n
        IF headers True: Create 2-D Array without buf
        """
        self.dgarray = np.ndarray(
            (self.lines, self.cols),
            dtype=np.int64,
            offset=self.__cfg.Profiling.offset,
            buffer=self.profiling_buf,
        )
        if headers:
            self.dgheaders = np.ndarray((6, self.cols), dtype=np.int64)
            self.dgheaders[:] = 0

    def set_status(self, id_m: int, code: int) -> bool | Exception:
        """
        IF code > 49: set code on StatusShM.buf[ID_M].\n
        Else, called func "_profiling_" that set code+time_ns on ProfilingShM.\n
        """
        try:
            if code > 49:
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

    def have_problem(self, id_m: int, proc=False, daugther=False) -> bool | Exception:
        """
        Get StatusCode Module|Proc.\n
        IF status_code == Warn|Error: return True. Else: return False
        """
        try:
            if proc:
                if self.status_buf[self.id_p] == 2:
                    return True

                return False

            else:
                if self.status_buf[id_m] > 49:
                    return True

                if daugther:
                    if self.status_buf[self.id_d] > 49:
                        return True

                return False

        except Exception as e:
            traceback.print_exc()  # Debug
            raise Exception(e)

    @staticmethod
    def dump_profile(
        file_path: str, _X_: np.ndarray | memoryview, _bin=False
    ) -> None | Exception:
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
