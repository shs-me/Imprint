import gc
import struct
import sys
import time
import traceback
from multiprocessing import Event, Process, Semaphore
from multiprocessing.shared_memory import SharedMemory
from typing import TypedDict

import tomllib
from loguru import logger

from .src import MonitorObj as mo
from .src import WatchDog, run_logic, run_monitoring, run_parsing, run_wss, run_wss_sim

PROCS = {
    10: {"name": "PARSING", "func": run_parsing, "proc": None},
    11: {"name": "LOGIC", "func": run_logic, "proc": None},
    12: {"name": "NETWORK", "func": None, "proc": None},
    13: {"name": "MONITORING", "func": run_monitoring, "proc": None},
    # BACKTESTING False | 12: ... "func": run_wss ...}
    # BACKTESTING True | 12: ... "func": run_wss_sim ...}
}

SHM_S = {
    "grid": {"shm": None, "buf": None},
    "raw": {"shm": None, "buf": None},
    "status": {"shm": None, "buf": None},
    "metrics": {"shm": None, "buf": None},
    "profiling": {"shm": None, "buf": None},
}


class ShmType(TypedDict):
    shm: SharedMemory
    buf: memoryview


class RunMain:
    def __init__(
        self,
        cfg: dict,
    ) -> None:
        self.cfg: dict = cfg
        self.sc_general: dict = {}
        self.profiling_dump = cfg["argg"]["profiling_dump"]
        self.status_file = cfg["argg"]["status_file"]
        # Event, Semaphores init
        # Module's sem's
        self.sem_sleep_parsing = Semaphore(0)
        self.sem_sleep_logic = Semaphore(0)
        # Profiling sem's
        self._parser_monitor = Semaphore(0)
        self._logic_monitor = Semaphore(0)
        self._network_monitor = Semaphore(0)
        # Admin sem's
        self.warn_error_status = Semaphore(0)
        self.general_event = Event()

        self.sem_s = [
            self.sem_sleep_parsing,
            self.sem_sleep_logic,
            self._parser_monitor,
            self._logic_monitor,
            self._network_monitor,
        ]

        # SharedMemory init
        self.shms: dict[str, ShmType] = SHM_S  # type: ignore
        self._shm_close()
        if self._shm_create() is False:
            # if true: shms get ShM obj | else: SysExit
            sys.exit()

        self._status_buf = self.shms["status"]["buf"]

        # self._procs init
        self._procs = PROCS
        self._procs[12]["func"] = (
            run_wss_sim if self.cfg["argg"]["backtesting"] else run_wss
        )

    @staticmethod
    def create(
        cfg_file: str,
    ) -> object | None:
        try:
            with open(cfg_file, "rb") as f:
                config = tomllib.load(f)

            return RunMain(
                cfg=config,
            )

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | Create | {e}")
            return None

    def _close_(
        self,
    ) -> None:
        try:
            logger.warning(
                "-- Core -- | _Exit | Closing Processes, SaveprofilingArray, Clean SHM-s, Exit..."
            )
            mo.dump_profile(
                self.profiling_dump, self.shms["profiling"]["buf"], _bin=True
            )
            for id, data in self._procs.items():
                if data["proc"] is not None and data["proc"].is_alive():
                    data["proc"].terminate()
                    data["proc"].join()
                    logger.warning(
                        f"-- Core -- | _Exit | Process {self._procs[id]['name']} closed"
                    )
            self._shm_close()

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | _Exit | {e}")

    # Close SharedMemory
    def _shm_close(
        self,
    ) -> None:
        for name in self.shms.keys():
            try:
                shm = SharedMemory(name=self.cfg["argg"][name]["shm"])
                shm.close()
                shm.unlink()

            except FileNotFoundError:
                pass

    # Open & Create SharedMemory
    def _shm_create(
        self,
    ) -> bool:
        try:
            for name in self.shms.keys():
                try:
                    shm = SharedMemory(
                        name=self.cfg["argg"][name]["shm"],
                        size=self.cfg["argg"][name]["bsize"],
                        create=True,
                    )

                except FileExistsError:
                    shm = SharedMemory(name=self.cfg["argg"][name]["shm"])

                self.shms[name]["shm"] = shm
                if isinstance(shm.buf, memoryview):
                    self.shms[name]["buf"] = shm.buf
                    self.shms[name]["buf"][:] = b"\x00" * self.shms[name]["shm"].size

            return True
        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | ShmControl | {e}")
            return False

    # Init arg proc
    def _proc_arg_init(
        self,
        proc_name,
    ) -> tuple | None:
        if proc_name == "PARSING":
            return (
                self.cfg["argg"],
                self.sem_sleep_parsing,
                self.sem_sleep_logic,
                self._parser_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "LOGIC":
            return (
                self.cfg["argg"],
                self.sem_sleep_logic,
                self._logic_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "NETWORK":
            return (
                self.cfg,
                self.sem_sleep_parsing,
                self._network_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "MONITORING":
            return (
                self.cfg["argg"],
                self.general_event,
                self._parser_monitor,
                self._logic_monitor,
                self._network_monitor,
                self.warn_error_status,
            )
        else:
            return None

    # Create & Run Procces's
    def _run_proc(
        self,
        id_proc,
    ) -> bool:
        try:
            if isinstance(id_proc, int):
                _arg = self._proc_arg_init(self._procs[id_proc]["name"])
                if isinstance(_arg, tuple):
                    p = Process(
                        target=self._procs[id_proc]["func"],
                        args=_arg,
                        name=self._procs[id_proc]["name"],
                        daemon=True,
                    )
                    p.start()
                    self._procs[id_proc]["proc"] = p
                    return True

                else:
                    logger.warning("-- Core -- | RunProc | Arg for Proc is not tuple")
                    return False

            else:
                logger.warning("-- Core -- | RunProc | proc_id is not int")
                return False

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | RunProc | {e}")
            return False

    # RunningCoreEngine
    def run_core_engine(
        self,
    ) -> bool | None:
        try:
            logger.info("--- Core --- Started. Init...")
            # Init Watchdog
            _watchdog = WatchDog.create(
                self._procs,
                self.shms,
                self.sem_s,
                self.general_event,
                self.warn_error_status,
                self.status_file,
            )
            # debug
            _offset = self.cfg["argg"]["metrics"]["tick_size"]
            self.shms["metrics"]["buf"][_offset: _offset+8] = (
                struct.pack("!d", 0.01)
            )
            # - - -
            if isinstance(_watchdog, WatchDog):
                self._sc = _watchdog.sc
                _run_watchdog_engine = _watchdog.run_watchdog_engine
                logger.info("WatchDog | Started")
                # Init Process's
                for id_proc in self._procs:
                    if self._run_proc(id_proc=id_proc) is False:
                        return False

                    time.sleep(0.5)

                self.general_event.set()  # pass
                logger.info("--- Core --- Init Completed.")
                try:
                    while True:
                        gc.collect()
                        if _run_watchdog_engine() is False:  # . . .
                            break

                except KeyboardInterrupt:
                    logger.warning("-- Core -- | RunCoreEngine | Shutting down bot")
                finally:
                    logger.warning(
                        "--- Core --- | RunCoreEngine | Closing because of the WatchDog"
                    )
            else:
                logger.warning(
                    "-- Core -- | RunCoreEngine | Create obj Watchdog failed"
                )

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | RunCoreEngine | {e}")
        finally:
            self._close_()


# Start Core Func
def run_core(
    cfg_path="core/config.toml",
):
    logger.remove()
    logger.add(
        "logs/__core__&_watchdog.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    gc.disable()

    state = RunMain.create(
        cfg_file=cfg_path,
    )
    if isinstance(state, RunMain):
        if state.run_core_engine() is False:
            logger.warning("-- Core -- | RunCoreEngine | RunProc in start failed")
            state._close_()
