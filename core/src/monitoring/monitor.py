import struct
import time
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Semaphore
from typing import TypedDict

import numpy as np

IDX_NAMES = {
    "parsing": {
        "shms": {
            "grid": {"shm": None, "buf": None},
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "metrics": {"shm": None, "buf": None},
            "profiling": {"shm": None, "buf": None},
        },
    },
    "logic": {
        "shms": {
            "grid": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "metrics": {"shm": None, "buf": None},
            "profiling": {"shm": None, "buf": None},
        },
    },
    "network": {
        "shms": {
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "profiling": {"shm": None, "buf": None},
        },
    },
    "network_sim": {
        "shms": {
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "profiling": {"shm": None, "buf": None},
        },
    },
    "profiling": {
        "shms": {
            "status": {"shm": None, "buf": None},
            "profiling": {"shm": None, "buf": None},
        },
    },
}


class ShmType(TypedDict):
    shm: SharedMemory
    buf: memoryview


class MonitorObj:
    def __init__(
        self,
        proc_name: str,
        config: dict,
        warn_error_status: Semaphore,
        _monitor: Semaphore | None = None,
        daughter: bool = False,
    ):
        # initializarion
        self.cfg: dict = config
        # ProfilingArray
        self.dglines: int = self.cfg["profiling"]["lines"]
        self.dgcols: int = self.cfg["profiling"]["cols"]
        self.offset: int = self.cfg["profiling"]["offset"]
        self.dgid = 0
        # SharedMemory-s
        self.shms: dict[str, ShmType] = IDX_NAMES[proc_name]["shms"]  # type: ignore
        # Semaphore, Event
        self._warn_error_status: Semaphore = warn_error_status
        if _monitor is not None:
            self._monitor = _monitor
        try:
            # LoadShm-s
            self._shm_init()

            # StatusSHM.buf
            self._status_buf = self.shms["status"]["buf"]
            # profilingSHM.buf
            self._profiling_buf = self.shms["profiling"]["buf"]
            if proc_name != "profiling":  # StatusSHM init
                # _id_m: Index parent module,
                # _id_p: Index parent proc
                self._id_p: int = self.cfg["status"][proc_name]["p"]
                self._id_m: int = self.cfg["status"][proc_name]["m"]
                self._id_d: int = self.cfg["status"][proc_name]["d"]
                self._dgc: int = self.cfg["status"][proc_name]["dgc"]

                self._profiling_array_init()

            else:
                self._profiling_array_init(headers=True)

        except Exception:
            traceback.print_exc()  # Debug
            raise Exception

    # Load SharedMemory-s, IF SHM not found raise FileNotFoundError
    def _shm_init(
        self,
    ) -> None | Exception:
        try:
            for name in self.shms.keys():
                shm = SharedMemory(
                    name=self.cfg[name]["shm"],
                )
                self.shms[name]["shm"] = shm
                if shm.buf is not None:
                    self.shms[name]["buf"] = shm.buf

        except FileNotFoundError as e:
            traceback.print_exc()  # Debug
            raise FileNotFoundError(e)

    # Create 2-D Array on buffer: ProfilingShm, without buf: Headers
    def _profiling_array_init(
        self,
        headers=False,
    ) -> None:
        self.dgarray = np.ndarray(
            (self.dglines, self.dgcols),
            dtype=np.int64,
            offset=self.offset,
            buffer=self._profiling_buf,
        )
        if headers:
            self.dgheaders = np.ndarray((6, self.dgcols), dtype=np.int64)
            self.dgheaders[:] = 0

    # For module's
    # Return ID_Dauhter or ID_"Parent".
    # Also set ID Parent on headers Profiling Shm
    def _status(
        self,
        daughter: bool = False,
    ) -> int:
        """
        Return ID_Dauhter, IF dauhter True \n
        Else, Return ID_Module "Parent".\n
        """
        if daughter:
            _id_m_ = self._id_d
        else:
            _id_m_, _dgc, _dg_buf = self._id_m, self._dgc, self._profiling_buf
            # Set ID Module on Headers ProfilingSHM
            _dg_buf[(64 + _dgc)] = _id_m_
            # Get Index Line & Status code from Profiling SHM headers
            self.dgid = struct.unpack_from("!i", _dg_buf[(_dgc * 8) : (_dgc * 8 + 4)])[
                0
            ]

        return _id_m_

    # For module's | MonitoringAgent | Watchdog
    # Set Status & TimeNS, If Warn & Error: StatusSHM, IF <10: ProfilingSHM
    def set_(
        self,
        id_m: int,
        code: int,
    ) -> bool | Exception:
        """
        IF code SET: IF code > 49 write on SHM_STATUS.BUF: index ID_M.\n
        Else, called "_profiling_array" that write code+time_ns on SHM_profiling.BUF.\n
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

    # Set TimeNS on 2-D Array, Buffer: Profiling Shm
    # Also set IndexLine & Status Code on Headers Profiling SHM
    def _profiling_(
        self,
        code: int,
    ) -> None:
        # profilingArray - LocalLinks
        dglines, dgarray, dgid_m, dgc, buf = (
            self.dglines,
            self.dgarray,
            self.dgid,
            self._dgc,
            self._profiling_buf,
        )
        # - - -
        dgarray[dgid_m, dgc] = time.time_ns()
        buf[(dgc * 8) : (dgc * 8 + 8)] = struct.pack(
            "!ii",
            dgid_m,
            code,
        )
        self.dgid = (dgid_m + 1) % dglines
        self._monitor.release()

    # Get Status Module or Proc if Warn & Error return True
    def get_(
        self,
        id_m: int,
        proc=False,
    ) -> bool | Exception:
        """
        Return True, if status module or proc: WARN,ERROR,STOPING,
        In other cases, return None
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

    # For MonitoringAgent | Main
    @staticmethod
    def dump_profile(
        file_path: str,
        _X_: np.ndarray | memoryview,
        _bin=False,
    ) -> None | Exception:
        try:
            if _bin:
                with open(file_path, "wb") as f:
                    f.write(_X_[:])
            else:
                if isinstance(_X_, np.ndarray):
                    np.savetxt(
                        file_path,
                        _X_,
                        delimiter=",",
                    )

        except Exception as e:
            traceback.print_exc()  # Debug
            raise Exception(e)
