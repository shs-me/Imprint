import os
import time
import traceback
from multiprocessing import Event, Process, Semaphore
from multiprocessing.shared_memory import SharedMemory

from loguru import logger

from . import (
    Config,
    IDpm,
    MonitorObj,
    ProcsCfg,
    ProcsDictTyping,
    ShMs,
    WatchDog,
)


class RunMain:
    def __init__(self, backtesting: bool) -> None:
        self.backtesting, self.core_cfg = backtesting, Config.CoreConfig
        self.procs: dict[int, ProcsDictTyping] = {}
        self.id_info, self.sc_general = {}, {}
        # Path's
        self.profiling_bin = Config.CorePath.profiling_bin
        # Proc's Event's
        self.sleep_parsing, self.sleep_logic = Event(), Event()
        # For profiling Semaphore's
        self.network_monitor, self.parser_monitor = Semaphore(0), Semaphore(0)
        self.logic_monitor = Semaphore(0)
        # Admin sem's
        self.warn_error_status, self.general_event = Semaphore(0), Event()
        self.sem_s = [
            self.parser_monitor,
            self.logic_monitor,
            self.network_monitor,
        ]

    def _init_session(self) -> bool:
        if self._shm_control(create=True, close=False):
            for _dir in Config.CorePath.dirs:
                if not os.path.exists(_dir):
                    os.mkdir(_dir)

            id_p = IDpm.network if self.backtesting else IDpm.network_sim
            self.procs, self.id_info = ProcsCfg.procs, Config.id_info
            self.procs.pop(id_p)
            self.id_info.pop(id_p)
            return True

        else:
            return False

    def _close_(self) -> None:
        try:
            logger.warning(
                "-- Core -- | _Exit | Closing Processes, DampProfilingArray, Clean SHM-s, Exit..."
            )
            MonitorObj.dump_profile(
                self.profiling_bin,
                self.buf[slice(*ShMs.profiling_offset)],
                _bin=True,
            )
            for id, data in self.procs.items():
                if data["proc"] is not None and data["proc"].is_alive():
                    data["proc"].terminate()
                    data["proc"].join()
                    logger.warning(
                        f"-- Core -- | _Exit | Process {self.procs[id]['name']} closed"
                    )

            self.buf.release()
            self._shm_control(create=False, close=True)

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | _Exit | {e}")

    def _shm_control(self, create: bool, close: bool) -> bool:
        """Open & Close & Create SharedMemory's"""
        try:
            if create:
                try:
                    self.shm = SharedMemory(
                        name=ShMs.shm_name, size=ShMs.shm_size, create=True
                    )
                except FileExistsError:
                    self.shm = SharedMemory(name=ShMs.shm_name)

                if self.shm.buf is not None:
                    self.buf = self.shm.buf
                    self.buf[:] = b"\x00" * self.shm.size

                return True

            if close:
                try:
                    self.shm.close()
                    self.shm.unlink()

                except FileNotFoundError:
                    pass

                return True

            return False

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | ShmControl | {e}")
            return False

    def _proc_arg_init(self, proc_name: str) -> tuple | None:
        if proc_name == "PARSING":
            return (
                self.sleep_parsing,
                self.sleep_logic,
                self.parser_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "LOGIC":
            return (
                self.sleep_logic,
                self.logic_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "NETWORK":
            return (
                self.sleep_parsing,
                self.network_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "NETWORK_SIM":
            return (
                self.sleep_parsing,
                self.network_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "MONITORING":
            return (
                self.backtesting,
                self.general_event,
                self.sem_s,
                self.warn_error_status,
            )
        else:
            return None

    def _run_proc(self, id_proc: int) -> bool:
        """Create & Run Procces's"""
        try:
            _arg = self._proc_arg_init(self.procs[id_proc]["name"])
            if isinstance(_arg, tuple):
                p = Process(
                    target=self.procs[id_proc]["func"],
                    args=_arg,
                    name=self.procs[id_proc]["name"],
                    daemon=True,
                )
                p.start()
                self.procs[id_proc]["proc"] = p
                return True

            else:
                logger.warning("-- Core -- | RunProc | Arg for Proc is not tuple")
                return False

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | RunProc | {e}")
            return False

    def run_core_engine(self) -> bool | None:
        try:
            logger.info("--- Core --- Started. Init...")
            if self._init_session() is False:
                return False

            _watchdog = WatchDog(
                procs=self.procs,
                id_info=self.id_info,
                shm_buf=self.buf,
                sem_s=self.sem_s,
                general_event=self.general_event,
                warn_error_status=self.warn_error_status,
            )
            logger.info("WatchDog | Started")
            for id_proc in self.procs:  # Init Process's
                if self._run_proc(id_proc=id_proc) is False:
                    return False

                time.sleep(0.5)

            self.general_event.set()
            logger.info("--- Core --- Init Completed.")
            try:
                while True:
                    if _watchdog.run_watchdog_engine() is False:
                        logger.warning(
                            "--- Core --- | RunCoreEngine | Closing because of the WatchDog"
                        )
                        break

            except KeyboardInterrupt:
                logger.warning("-- Core -- | RunCoreEngine | Shutting down bot")

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | RunCoreEngine | {e}")
        finally:
            self._close_()


def run_core(backtesting: bool = True) -> None:
    logger.remove()
    logger.add(
        Config.CorePath.core_log,
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    state = RunMain(backtesting=backtesting)
    if state.run_core_engine() is False:
        logger.warning("-- Core -- | RunCoreEngine | RunProc in start failed")
        state._close_()
