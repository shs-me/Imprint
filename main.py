import gc
import sys
import time
from multiprocessing import Event, Process, Semaphore
from multiprocessing.shared_memory import SharedMemory
from typing import TypedDict

import tomllib
from loguru import logger

from src.backtesting.wss_sim import run_wss_sim
from src.logic.logic_agent import run_logic
from src.monitoring.monitoring_agent import run_monitoring
from src.network.wss_proc import run_wss
from src.parsing.parser_agent import run_parsing

AGENTS = {
    9: {"name": "MONITOR", "func": run_monitoring, "proc": None},
    0: {"name": "PARSING", "func": run_parsing, "proc": None},
    3: {"name": "LOGIC", "func": run_logic, "proc": None},
    # BACKTESTING False | 6: {"name": "NETWORK", "func": run_wss, "proc": None},
    # BACKTESTING True | 6: {"name": "NETWORK", "func": run_wss_sim, "proc": None}
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

        # Event, Semaphores init
        self.sem_sleep_main = Semaphore(0)
        self.sem_sleep_parsing = Semaphore(0)
        self.sem_sleep_logic = Semaphore(0)

        self.warn_error_status = Event()
        self.general_event = Event()

        self.general_event.set()

        # SharedMemory configuration
        self.shms: dict[str, ShmType] = SHM_S  # type: ignore
        if (
            self._shm_control(create=True) is False
        ):  # if true: shms get Memory objects | else: SysExit
            sys.exit()

        # StatusSHM init
        self.id_pm = self.cfg["argg"]["status"][
            "monitoring"
        ]  # Index Process Monitoring on StatusSHM
        self.id_main = self.cfg["argg"]["status"]["main"]

        self.smt = 0  # Status Monitoring Task

    @staticmethod
    def create(**argg):
        try:
            with open(argg["config_file"], "rb") as f:
                config = tomllib.load(f)

            return StartMain(
                cfg=config,
            )

        except Exception as e:
            logger.error(e)
            return None

    def _get_sem(
        self,
        id,
    ):
        if id == "PARSING":
            return (
                self.cfg["argg"],
                self.sem_sleep_parsing,
                self.sem_sleep_logic,
                self.general_event,
                self.warn_error_status,
            )
        elif id == "LOGIC":
            return (
                self.cfg["argg"],
                self.sem_sleep_logic,
                self.general_event,
                self.warn_error_status,
            )
        elif id == "NETWORK":
            return (
                self.cfg,
                self.sem_sleep_parsing,
                self.general_event,
                self.warn_error_status,
            )
        elif id == "MONITOR":
            return (self.cfg["argg"], self.sem_sleep_main, self.warn_error_status)

    def _exit(
        self,
    ):
        try:
            for id, data in AGENTS.items():
                if data["proc"] is not None and data["proc"].is_alive():
                    data["proc"].terminate()
                    data["proc"].join()
                    logger.warning(f"Process {AGENTS[id]['name']} closed")

            self._shm_clean()
            logger.warning("Clean SHM-s, Exit...")
            sys.exit()

        except Exception as e:
            logger.error(e)
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
            logger.error(e)
            return False

    def _run_proc(
        self,
        id,
    ):
        try:
            p = Process(
                target=AGENTS[id]["func"],
                args=self._get_sem(AGENTS[id]["name"]),  # type: ignore
                name=AGENTS[id]["name"],
                daemon=True,
            )
            p.start()
            AGENTS[id]["proc"] = p

        except Exception as e:
            logger.error(e)
            return False

    def _check_proc(
        self,
        id,
        attempt=2,
    ):
        try:
            for _ in range(attempt):
                if AGENTS[id]["proc"].is_alive() is not True:
                    logger.warning(
                        f"Process {AGENTS[id]['name']} is dead. Restarting..."
                    )
                    self._run_proc(id)
                    if AGENTS[id]["proc"].is_alive() is not True:
                        time.sleep(0.5)
                    else:
                        return True

                else:
                    return True

            logger.warning(f"Failed to run {AGENTS[id]['name']} Process.")
            return False

        except Exception as e:
            logger.error(e)
            return False

    def _exc_m_tasks(
        self,
    ):  # Execution Monitoring _exc_m_tasks
        while True:
            try:
                self.smt = self.shms["status"]["buf"][self.id_pm]
                if self.smt == 3:
                    logger.warning(
                        f"Process {AGENTS[self.id_pm]['name']} Fell because of Unidentified Error. Closing Bot"
                    )
                    return False

                elif self.smt == 1 or self.smt == 200:
                    break

                elif self._check_proc(id=self.id_pm):
                    if self.smt == 0:
                        for id_proc in AGENTS:
                            if self._check_proc(id=id_proc, attempt=1) is False:
                                return False

                    elif self.smt >= 100 and 106 >= self.smt:
                        if self._check_proc(id=(self.smt - 100)):
                            break
                        else:
                            return False

                    elif self.smt == 201:
                        if self._shm_control() is False:
                            return False

                        self.general_event.set()
                        for id_proc in AGENTS:
                            if self._check_proc(id=id_proc, attempt=1) is False:
                                return False

                else:
                    return False

                break

            except Exception as e:
                logger.error(e)
                return False

    def run_main(
        self,
    ):
        logger.info("--- MAIN --- Started. Init...")
        # AGENTS init
        NETWORK = {"name": "NETWORK", "func": run_wss, "proc": None}
        NETWORK_SIM = {"name": "NETWORK", "func": run_wss_sim, "proc": None}

        AGENTS[5] = NETWORK_SIM if self.cfg["argg"]["backtesting"] else NETWORK
        for id_proc in AGENTS:
            if self._run_proc(id=id_proc) is False:
                self.shms["status"]["buf"][self.id_main] = 150  # Error
                break

            time.sleep(1)

        logger.info("--- MAIN --- Init Completed.")
        try:
            while True:
                gc.collect()
                self.general_event.clear()
                self.sem_sleep_main.acquire(timeout=60)

                if self._exc_m_tasks() is False:
                    break

        except KeyboardInterrupt:
            logger.warning("Shutting down bot")
        except Exception as e:
            logger.error(e)
        finally:
            self._exit()


if __name__ == "__main__":
    logger.remove()
    logger.add(
        f"logs/{__name__}.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
    )

    gc.disable()

    state = StartMain.create(
        config_file="config.toml",
    )
    if isinstance(state, StartMain):
        state.run_main()
