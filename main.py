import gc
import sys
import time
import traceback
from multiprocessing import Event, Process, Semaphore
from multiprocessing.shared_memory import SharedMemory
from typing import TypedDict

import tomllib
from loguru import logger

from src.backtesting.wss_sim import run_wss_sim
from src.logic.logic_agent import run_logic
from src.monitoring import run_monitoring
from src.network.wss_proc import run_wss
from src.parsing.parser_agent import run_parsing
from src.utils import StatusAgent as sa
from src.watchdog import WatchDog

PROCS = {
    13: {"name": "MONITORING", "func": run_monitoring, "proc": None},
    10: {"name": "PARSING", "func": run_parsing, "proc": None},
    11: {"name": "LOGIC", "func": run_logic, "proc": None},
    12: {"name": "NETWORK", "func": None, "proc": None},
    # BACKTESTING False | 12: ... "func": run_wss ...}
    # BACKTESTING True | 12: ... "func": run_wss_sim ...}
}

SHM_S = {
    "grid": {"shm": None, "buf": None},
    "raw": {"shm": None, "buf": None},
    "status": {"shm": None, "buf": None},
    "sign": {"shm": None, "buf": None},
    "debug": {"shm": None, "buf": None},
}


class ShmType(TypedDict):
    shm: SharedMemory
    buf: memoryview


class StartMain:
    def __init__(
        self,
        cfg: dict,
    ):
        self.cfg: dict = cfg
        self.sc_general: dict = {}
        self.dgarray_file = cfg["argg"]["dgarray_file"]
        self.status_file = cfg["argg"]["status_file"]
        # Event, Semaphores init
        self.sem_sleep_parsing = Semaphore(0)
        self.sem_sleep_logic = Semaphore(0)

        self._parser_monitor = Semaphore(0)
        self._logic_monitor = Semaphore(0)
        self._network_monitor = Semaphore(0)

        self.warn_error_status = Semaphore()
        self.general_event = Event()

        self.general_event.set()

        # SharedMemory init
        self.shms: dict[str, ShmType] = SHM_S  # type: ignore
        if (
            self._shm_control(create=True) is False
        ):  # if true: shms get Memory objects | else: SysExit
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
    ):
        try:
            with open(cfg_file, "rb") as f:
                config = tomllib.load(f)

            return StartMain(
                cfg=config,
            )

        except Exception as e:
            traceback.print_exc()
            logger.error(f"-- MAIN -- | Create | {e}")
            return None

    def _proc_arg_init(
        self,
        proc_name,
    ):
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
                self._sc["ID_INFO"],
                self._sc["GENERAL"],
                self.general_event,
                self._parser_monitor,
                self._logic_monitor,
                self._network_monitor,
            )

    def _sem_clean(
        self,
    ):
        try:
            for sem in [self.sem_sleep_parsing, self.sem_sleep_logic]:
                while sem.acquire(block=False):
                    pass
            return True

        except Exception as e:
            traceback.print_exc()
            logger.error(f"-- MAIN -- | SemClean | {e}")
            return False

    def _exit(
        self,
    ):
        try:
            logger.warning(
                "-- MAIN -- | _Exit | Closing Processes, SaveDebugArray, Clean SHM-s, Exit..."
            )
            sa.save_array(self.shms["debug"]["buf"], self.dgarray_file)
            for id, data in self._procs.items():
                if data["proc"] is not None and data["proc"].is_alive():
                    data["proc"].terminate()
                    data["proc"].join()
                    logger.warning(
                        f"-- Main -- | _Exit | Process {self._procs[id]['name']} closed"
                    )

            self._shm_clean()
            sys.exit()

        except Exception as e:
            logger.error(f"-- MAIN -- | _Exit | {e}")
            sys.exit()

    def _shm_clean(
        self,
    ):
        for name in self.shms.keys():
            try:
                shm = SharedMemory(name=self.cfg["argg"][name]["shm"])
                shm.close()
                shm.unlink()

            except FileNotFoundError:
                pass

    def _shm_control(
        self,
        create=False,
    ):
        try:
            for name in self.shms.keys():
                if create:
                    shm = SharedMemory(
                        name=self.cfg["argg"][name]["shm"],
                        size=self.cfg["argg"][name]["bsize"],
                        create=True,
                    )
                    self.shms[name]["shm"] = shm
                    if isinstance(shm.buf, memoryview):
                        self.shms[name]["buf"] = shm.buf

                self.shms[name]["buf"][:] = b"\x00" * self.shms[name]["shm"].size

        except Exception as e:
            traceback.print_exc()
            logger.error(f"-- MAIN -- | ShmControl | {e}")
            return False

    def _run_proc(
        self,
        id_proc,
    ):
        try:
            if isinstance(id_proc, int):
                p = Process(
                    target=self._procs[id_proc]["func"],
                    args=self._proc_arg_init(self._procs[id_proc]["name"]),  # type: ignore
                    name=self._procs[id_proc]["name"],
                    daemon=True,
                )
                p.start()
                self._procs[id_proc]["proc"] = p

            else:
                logger.warning("-- MAIN -- | RunProc | proc_id is not int")

        except Exception as e:
            traceback.print_exc()
            logger.error(f"-- MAIN -- | RunProc | {e}")
            return False

    def _check_proc(
        self,
        id_proc,
    ):
        try:
            if self._procs[id_proc]["proc"].is_alive() is not True:
                logger.warning(
                    f"-- MAIN -- | CheckProc | Process {self._procs[id_proc]['name']} is dead. Restarting..."
                )
                self._run_proc(id_proc)
                if self._procs[id_proc]["proc"].is_alive() is not True:
                    time.sleep(0.5)
                else:
                    return True

            else:
                return True

            logger.warning(
                f"-- MAIN -- | CheckProc | Failed to run {self._procs[id_proc]['name']} Process."
            )
            return False

        except Exception as e:
            traceback.print_exc()
            logger.error(f"-- MAIN -- | CheckProc | {e}")
            return False

    def _exc_m_tasks(
        self,
        task: int,
    ):
        while True:
            try:
                if task == 0:
                    for id_proc in self._procs:
                        if self._check_proc(id_proc=id_proc) is False:
                            return False

                elif 100 <= task <= 106:
                    if self._check_proc(id_proc=(task - 100)):
                        break
                    else:
                        return False

                elif task == 201:
                    if self._shm_control() is not False:
                        if self._sem_clean() is not False:
                            self.general_event.set()
                            for id_proc in self._procs:
                                if self._check_proc(id_proc=id_proc) is False:
                                    return False
                        else:
                            return False
                    else:
                        return False
                else:
                    return False

                break

            except Exception as e:
                traceback.print_exc()
                logger.error(f"-- MAIN -- | ExcWTasks | {e}")
                return False

    def run_main(
        self,
    ):
        logger.info("--- MAIN --- Started. Init...")
        _watchdog = WatchDog.create(
            self._status_buf,
            self.warn_error_status,
            self.status_file,
        )
        if isinstance(_watchdog, WatchDog):
            self._sc = _watchdog.sc
            _run_watchdog_engine = _watchdog.run_watchdog_engine
            for id_proc in self._procs:
                if self._run_proc(id_proc=id_proc) is False:
                    break

                time.sleep(1)

            logger.info("--- MAIN --- Init Completed.")
            try:
                while True:
                    gc.collect()
                    self.general_event.clear()

                    if (task := _run_watchdog_engine()) is not False:
                        if self._exc_m_tasks(task) is not False:
                            continue
                    break

            except KeyboardInterrupt:
                logger.warning("-- MAIN -- | RunMain | Shutting down bot")
            except Exception as e:
                traceback.print_exc()
                logger.error(f"-- MAIN -- | RunMain | {e}")
            finally:
                self._exit()
        else:
            self._exit()


if __name__ == "__main__":
    logger.remove()
    logger.add(
        f"logs/{__name__}.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    gc.disable()

    state = StartMain.create(
        cfg_file="config.toml",
    )
    if isinstance(state, StartMain):
        state.run_main()
