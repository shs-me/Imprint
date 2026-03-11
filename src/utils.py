import time
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event
from typing import TypedDict

import numpy as np

IDX_NAMES = {
    "parsing": {
        "cols": {"p": "0", "m": "1", "d": "2"},
        "shm_names": {
            "grid": {"shm": None, "buf": None},
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "sign": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
    "logic": {
        "cols": {"p": "3", "m": "4", "d": "5"},
        "shm_names": {
            "grid": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "sign": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
    "network": {
        "cols": {"p": "6", "m": "7", "d": "8"},
        "shm_names": {
            "raw": {"shm": None, "buf": None},
            "status": {"shm": None, "buf": None},
            "debug": {"shm": None, "buf": None},
        },
    },
    "network_sim": {
        "cols": {"p": "6", "m": "11", "d": "12"},
        "shm_names": {
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
        warn_error_status: Event,
        daughter: bool = False,
    ):
        # initializarion
        self.cfg: dict = config
        self._warn_error_status: Event = warn_error_status
        try:
            # SharedMemory-s
            self.shms: dict[str, ShmType] = IDX_NAMES[proc_name]["shm_names"]
            # StatusSHM init, _id_m: Index parent module, _id_p: Index parent proc
            self._id_p: int = int(IDX_NAMES[proc_name]["cols"]["p"])
            self._id_d = int(IDX_NAMES[proc_name]["cols"]["d"])
            self._id_m = int(IDX_NAMES[proc_name]["cols"]["m"])
            # LoadShm-s
            self._shm_init()

            # StatusSHM.buf
            self._status_buf = self.shms["status"]["buf"]
            # DebugSHM.buf
            self._debug_buf = self.shms["debug"]["buf"]

            # DebugArray
            self.dglines: int = self.cfg["debug"]["lines"]
            self.dgcols: int = self.cfg["debug"]["cols"]
            self._current_id = 0
            self._debug_array_init()

        except Exception:
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
            return self._id_d
        else:
            return self._id_m

    def set_(
        self,
        id_m: int,
        code: int | None = None,
    ):
        """
        IF code SET: IF code > 49 write on SHM_STATUS.BUF: index ID_M.\n
        Else, called "_debug_array" that write code on SHM_DEBUG.BUF.\n
        IF code NOT SET: called "_debug_array",\n
        that write current "time_ns" on SHM_DEBUG.BUF.\n
        """
        try:
            if code:
                if code > 49:
                    self._status_buf[id_m] = code
                    self._warn_error_status.set()

                else:
                    self._debug_array(id_m, code)

            else:
                self._debug_array(id_m)

        except Exception:
            raise Exception

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

        except Exception:
            raise Exception

    def _debug_array(
        self,
        id_m: int,
        code: None | int = None,
    ):
        try:
            if (self.dglines - 2) == self._current_id:
                self._current_id = 0

            if code:
                self.dgarray[self._current_id, id_m] = code
            else:
                self.dgarray[self._current_id, id_m] = time.time_ns()

            self._current_id += 1
            self.dgarray[self.dglines - 1, id_m] = self._current_id

        except Exception:
            raise Exception

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
            raise Exception(e)
