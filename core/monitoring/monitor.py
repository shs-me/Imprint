import struct
import time
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Semaphore

import numpy as np

from .. import Config, ShmType


class MonitorObj:
    def __init__(
        self,
        proc_name: str,
        warn_error_status: Semaphore,
        _monitor: Semaphore | None = None,
    ):
        # Initialization
        self.core_cfg = Config.CoreConfig()
        # ProfilingArray
        self.dglines: int = self.core_cfg.Profiling.lines
        self.dgcols: int = self.core_cfg.Profiling.cols
        self.offset: int = self.core_cfg.Profiling.offset
        # SharedMemory init
        self.shms: dict[str, ShmType] = {  # type: ignore
            self.core_cfg.Grid.__name__: {},
            self.core_cfg.Raw.__name__: {},
            self.core_cfg.Status.__name__: {},
            self.core_cfg.Metrics.__name__: {},
            self.core_cfg.Profiling.__name__: {},
        }
        # Semaphore, Event
        self._warn_error_status: Semaphore = warn_error_status
        try:
            # LoadShm-s
            self._shm_init()
            # StatusSHM.buf
            self._status_buf = self.shms[Config.CoreConfig.Status.__name__]["buf"]
            # profilingSHM.buf
            self._profiling_buf = self.shms[Config.CoreConfig.Profiling.__name__]["buf"]
            if proc_name != Config.CoreConfig.Profiling.__name__:  # StatusSHM init
                if _monitor is not None:
                    self._monitor = _monitor

                _obj = getattr(self.core_cfg.Status, proc_name)
                self._id_p: int = _obj.id_p
                self._id_m: int = _obj.id_m
                self._id_d: int = _obj.id_d
                self._dgc: int = _obj.id_dgc
                self._profiling_array_init()
                # Set ID Module on Headers ProfilingSHM
                self._profiling_buf[(64 + self._dgc)] = self._id_m
                # Get Index Line & Status code from Profiling SHM headers
                self.dgid: int = struct.unpack_from(
                    "!i", self._profiling_buf[(self._dgc * 8) : (self._dgc * 8 + 4)]
                )[0]

            else:
                self._profiling_array_init(headers=True)

        except Exception:
            traceback.print_exc()  # Debug
            raise Exception

    def _shm_init(self) -> None | Exception:
        """Load SharedMemory-s, IF SHM not found, raise FileNotFoundError"""
        try:
            for name in self.shms.keys():
                _obj = getattr(self.core_cfg, name)
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
            (self.dglines, self.dgcols),
            dtype=np.int64,
            offset=self.offset,
            buffer=self._profiling_buf,
        )
        if headers:
            self.dgheaders = np.ndarray((6, self.dgcols), dtype=np.int64)
            self.dgheaders[:] = 0

    def set_(self, id_m: int, code: int) -> bool | Exception:
        """
        IF code > 49: set code on StatusShM.buf[ID_M].\n
        Else, called func "_profiling_" that set code+time_ns on ProfilingShM.\n
        """
        try:
            if code > 49:
                self._status_buf[id_m] = code
                self._warn_error_status.release()
                return True
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
        # LocalLinks
        dglines, dgarray = self.dglines, self.dgarray
        dgid_m, dgc, buf = self.dgid, self._dgc, self._profiling_buf
        # - - -
        dgarray[dgid_m, dgc] = time.time_ns()
        buf[(dgc * 8) : (dgc * 8 + 8)] = struct.pack(
            "!ii",
            dgid_m,
            code,
        )
        self.dgid = (dgid_m + 1) % dglines
        self._monitor.release()

    def get_(self, id_m: int, proc=False) -> bool | Exception:
        """
        Get StatusCode Module|Proc.\n
        IF status_code == Warn|Error: return True. Else: return False
        """
        try:
            if proc:
                if self._status_buf[self._id_p] == 2:
                    return True

                return False

            else:
                if self._status_buf[id_m] > 49:
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
