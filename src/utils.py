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
            "sign": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
    "logic": {
        "shms": {
            "grid": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "sign": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
    "network": {
        "shms": {
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
    "network_sim": {
        "shms": {
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
}


class ShmType(TypedDict):
    shm: SharedMemory
    buf: memoryview


class StatusAgent:
    def __init__(
        self,
        proc_name: str,
        config: dict,
        warn_error_status: Semaphore,
        sem_sleep_monitoring: Semaphore,
        daughter: bool = False,
    ):
        # initializarion
        self.cfg: dict = config
        self.sem_sleep_monitoring = sem_sleep_monitoring
        self._warn_error_status: Semaphore = warn_error_status
        try:
            # SharedMemory-s
            self.shms: dict[str, ShmType] = IDX_NAMES[proc_name]["shms"]  # type: ignore
            # StatusSHM init, _id_m: Index parent module, _id_p: Index parent proc
            self._id_p: int = self.cfg["status"][proc_name]["p"]
            self._id_m: int = self.cfg["status"][proc_name]["m"]
            self._id_d: int = self.cfg["status"][proc_name]["d"]
            # LoadShm-s
            self._shm_init()

            # StatusSHM.buf
            self._status_buf = self.shms["status"]["buf"]
            # DebugSHM.buf
            self._debug_buf = self.shms["debug"]["buf"]

            # DebugArray
            self.dglines: int = self.cfg["debug"]["lines"]
            self.dgcols: int = self.cfg["debug"]["cols"]
            self.offset: int = self.cfg["debug"]["offset"]
            self._dgc: int = self.cfg["status"][proc_name]["dgc"]
            self.dgid = 0
            self._debug_array_init()

        except Exception:
            traceback.print_exc()
            raise Exception

    def _shm_init(
        self,
    ):  # Load SharedMemory-s
        for name in self.shms.keys():
            shm = SharedMemory(
                name=self.cfg[name]["shm"],
            )
            self.shms[name]["shm"] = shm
            if shm.buf is not None:
                self.shms[name]["buf"] = shm.buf

    def _debug_array_init(
        self,
    ):  # Create Array on buffer
        self.dgarray = np.ndarray(
            (self.dglines, self.dgcols),
            dtype=np.int64,
            offset=self.offset,
            buffer=self._debug_buf,
        )

    def _status(
        self,
        daughter: bool = False,
    ):
        """
        Return ID_Dauhter, IF dauhter True \n
        Else, Return ID_Module "Parent".\n
        """
        if daughter:
            _id_m_ = self._id_d
        else:
            _id_m_, _dgc, _dg_buf = self._id_m, self._dgc, self._debug_buf
            _dg_buf[(64 + _dgc)] = _id_m_
            self.dgid = struct.unpack_from(
                "!i", _dg_buf[(_dgc * 8 + 8 - 8) : (_dgc * 8 + 4)]
            )[0]

        return _id_m_

    def set_(
        self,
        id_m: int,
        code: int,
    ):
        """
        IF code SET: IF code > 49 write on SHM_STATUS.BUF: index ID_M.\n
        Else, called "_debug_array" that write code+time_ns on SHM_DEBUG.BUF.\n
        """
        try:
            if code:
                if code > 49:
                    self._status_buf[id_m] = code
                    self._warn_error_status.release()

                else:
                    self._debug_array(id_m)

            else:
                self._debug_array(id_m)

        except Exception as e:
            traceback.print_exc()
            raise Exception(e)

    def get_(
        self,
        id_m: int,
        proc=False,
    ):  # Get Status Module or Proc if True
        """
        Return True, if status module or proc: WARN,ERROR,STOPING,
        In other cases, return None
        """
        try:
            if proc:
                if self._status_buf[self._id_p] == 2:
                    return True

                return

            else:
                if self._status_buf[id_m] > 49:
                    return True

                return

        except Exception as e:
            traceback.print_exc()
            raise Exception(e)

    def _debug_array(
        self,
        code: int,
    ):
        # DebugArrat - LocalLinks
        dglines, dgarray, dgid_m, dgc, buf = (
            self.dglines,
            self.dgarray,
            self.dgid,
            self._dgc,
            self._debug_buf,
        )
        # - - -
        dgarray[dgid_m, dgc] = time.time_ns()
        buf[(dgc * 8 + 8 - 8) : (dgc * 8 + 8)] = struct.pack(
            "!ii",
            dgid_m,
            code,
        )
        self.dgid = (dgid_m + 1) % dglines
        self.sem_sleep_monitoring.release()

    @staticmethod
    def save_array(
        buf: memoryview,
        file_path: str,
    ):
        """
        DUMP shm buf to File.bin. \n
        Shape config[DebugLines, DebugCols], dtype: np.int64.
        """
        try:
            with open(file_path, "wb") as f:
                f.write(buf[:])

        except Exception as e:
            traceback.print_exc()
            raise Exception(e)
