import struct
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
    ShmType,
    StatusCodes,
    WatchDog,
)


class RunMain:
    def __init__(self, backtesting: bool) -> None:
        # Initialization
        self.backtesting = backtesting
        self.procs: dict[int, ProcsDictTyping] = {}
        self.id_info = {}
        self.core_cfg = Config.CoreConfig()
        self.profiling_bin = Config.CorePath.profiling_bin
        self.status_json = Config.CorePath.status_json
        self.sc_general = {}
        # Event, Semaphores init
        # Module's sem's | Event's
        self.sem_sleep_parsing = Semaphore(0)
        self.sleep_logic = Event()
        # Profiling sem's
        self._parser_monitor = Semaphore(0)
        self._logic_monitor = Semaphore(0)
        self._network_monitor = Semaphore(0)
        # Admin sem's
        self.warn_error_status = Semaphore(0)
        self.general_event = Event()
        self.sem_s = [
            self.sem_sleep_parsing,
            self._parser_monitor,
            self._logic_monitor,
            self._network_monitor,
        ]
        # SharedMemory init
        self.shms: dict[str, ShmType] = {  # type: ignore
            self.core_cfg.Grid.__name__: {},
            self.core_cfg.Raw.__name__: {},
            self.core_cfg.Status.__name__: {},
            self.core_cfg.Metrics.__name__: {},
            self.core_cfg.Profiling.__name__: {},
        }

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
                self.sem_sleep_parsing,
                self.sleep_logic,
                self._parser_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "LOGIC":
            return (
                self.sleep_logic,
                self._logic_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "NETWORK":
            return (
                self.sem_sleep_parsing,
                self._network_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "NETWORK_SIM":
            return (
                self.sem_sleep_parsing,
                self._network_monitor,
                self.general_event,
                self.warn_error_status,
            )
        elif proc_name == "MONITORING":
            return (
                self.backtesting,
                self.general_event,
                self._parser_monitor,
                self._logic_monitor,
                self._network_monitor,
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

            _watchdog = WatchDog.create(
                procs=self.procs,
                id_info=self.id_info,
                shm_s=self.shms,
                sem_s=self.sem_s,
                general_event=self.general_event,
                sleep_logic=self.sleep_logic,
                warn_error_status=self.warn_error_status,
                file_path=self.status_json,
            )
            # debug
            _start, _end = self.core_cfg.Metrics.tick_size
            self.shms[Config.CoreConfig.Metrics.__name__]["buf"][_start:_end] = (
                struct.pack("!d", 0.01)
            )
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
