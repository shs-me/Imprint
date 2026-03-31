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
    ShmType,
    StatusCodes,
    WatchDog,
)


class RunMain:
    def __init__(self, backtesting: bool) -> None:
        self.backtesting, self.core_cfg = backtesting, Config.CoreConfig
        self.procs: dict[int, ProcsDictTyping] = {}
        self.id_info, self.sc_general = {}, {}
        # Path's
        self.profiling_bin = Config.CorePath.profiling_bin
        self.status_json = Config.CorePath.status_json
        # SharedMemory's | Memoryview's
        self.shms: dict[str, ShmType] = ShMs.shms
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

    def _close_(self) -> None:
        try:
            logger.warning(
                "-- Core -- | _Exit | Closing Processes, SaveprofilingArray, Clean SHM-s, Exit..."
            )
            MonitorObj.dump_profile(
                self.profiling_bin,
                self.shms[Config.CoreConfig.Profiling.__name__]["buf"],
                _bin=True,
            )
            for id, data in self.procs.items():
                if data["proc"] is not None and data["proc"].is_alive():
                    data["proc"].terminate()
                    data["proc"].join()
                    logger.warning(
                        f"-- Core -- | _Exit | Process {self.procs[id]['name']} closed"
                    )
            self._shm_close()

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | _Exit | {e}")

    def _shm_close(self) -> None:
        """Close SharedMemory's"""
        for name in self.shms.keys():
            try:
                _obj = getattr(self.core_cfg, name)
                shm = SharedMemory(name=_obj.shm_name)
                shm.close()
                shm.unlink()

            except FileNotFoundError:
                pass

    def _shm_create(self) -> bool:
        """Open & Create SharedMemory's"""
        try:
            for name in self.shms.keys():
                try:
                    _obj = getattr(self.core_cfg, name)
                    shm = SharedMemory(
                        name=_obj.shm_name,
                        size=_obj.shm_size,
                        create=True,
                    )

                except FileExistsError:
                    _obj = getattr(self.core_cfg, name)
                    shm = SharedMemory(name=_obj.shm_name)

                if shm.buf is not None:
                    self.shms[name]["shm"] = shm
                    self.shms[name]["buf"] = shm.buf
                    self.shms[name]["buf"][:] = b"\x00" * self.shms[name]["shm"].size
                else:
                    return False

            return True
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
            self.procs, self.id_info = ProcsCfg.procs, StatusCodes.id_info
            _key = IDpm.network if self.backtesting else IDpm.network_sim
            self.procs.pop(_key)
            self.id_info.pop(_key)
            self._shm_close()
            if self._shm_create() is False:
                return False

            _watchdog = WatchDog(
                procs=self.procs,
                id_info=self.id_info,
                shm_s=self.shms,
                sem_s=self.sem_s,
                general_event=self.general_event,
                warn_error_status=self.warn_error_status,
            )
            # debug
            _start, _end = self.core_cfg.Metrics.tick_size
            __cfg = Config.CoreConfig
            tick_size_buf = self.shms[__cfg.Metrics.__name__]["buf"][
                __cfg.Metrics.tick_size[0] : __cfg.Metrics.tick_size[1]
            ].cast("d")
            tick_size_buf[0] = 0.01
            # - - -
            if isinstance(_watchdog, WatchDog):
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

            else:
                logger.warning(
                    "-- Core -- | RunCoreEngine | Create obj Watchdog failed"
                )

        except Exception as e:
            traceback.print_exc()  # Debug
            logger.error(f"-- Core -- | RunCoreEngine | {e}")
        finally:
            self._close_()


def run_core(backtesting: bool = True) -> None:
    logger.remove()
    logger.add(
        "logs/__core__&_watchdog.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    state = RunMain(backtesting=backtesting)
    if state.run_core_engine() is False:
        logger.warning("-- Core -- | RunCoreEngine | RunProc in start failed")
        state._close_()
