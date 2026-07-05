import inspect
import os
from multiprocessing import Event, Process, Semaphore
from multiprocessing.synchronize import Event as EventT
from multiprocessing.synchronize import Semaphore as SemT
from types import FunctionType

from loguru import logger

from .constant import CORE_LOG_PATH, DIRS_LIST
from .engine.mode.backtest.execution_sim_agent import run_execution_sim
from .engine.mode.backtest.logic_sim_agent import run_logic_sim
from .engine.mode.backtest.parsing_sim_agent import run_parsing_sim
from .engine.mode.backtest.rest_sim_agent import RestSimAgent
from .engine.mode.backtest.wss_sim_agent import run_wss_sim
from .engine.mode.real.execution_agent import run_execution
from .engine.mode.real.logic_agent import run_logic
from .engine.mode.real.parsing_agent import run_parsing
from .engine.mode.real.rest_agent import RestAgent
from .engine.mode.real.wss_agent import run_wss
from .settings import CoreResources
from .utils.monitoring.main_manager import MainManager
from .utils.monitoring.office import manager_office
from .utils.tools import download_aggTrade_hist_daily_data, to_date


class RunMain(CoreResources):
    def __init__(self, **kwargs) -> None:
        self.baseKwargs: dict = kwargs
        self.symbol: str = kwargs["symbol"]
        self.backtesting: bool = kwargs["backtesting"]
        self.execution: bool = kwargs["execution"]
        self.manager: MainManager = kwargs.pop("manager")

        self.cfgBacktesting = self.manager.cfgBacktesting
        # CoreResources
        self.general_event: EventT = Event()
        self.execution_event: EventT = Event()
        self.parsing_event: EventT = Event()
        self.logic_event: EventT = Event()
        self.sc_sem: SemT = Semaphore(0)
        # Variable's
        self.procs: dict = {}
        self.funcs: list[FunctionType] = []
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""

    def check_dirs(self) -> None:
        for _dir in DIRS_LIST:
            if not os.path.exists(_dir):
                os.mkdir(_dir)

    def check_data(self) -> None:
        if self.backtesting:
            try:
                startDate, endDate = to_date(
                    [
                        self.manager.cfgBacktesting.startDateForPrepper,
                        self.manager.cfgBacktesting.endDateForPrepper,
                    ]
                )
            except ValueError as e:
                return logger.error(f"-- Core -- | {e}")

            download_aggTrade_hist_daily_data(self.symbol, startDate, endDate)

    def init_funcs(self) -> None:
        if self.backtesting:
            self.rest = RestSimAgent(self.symbol, self.cfgBacktesting)
        else:
            self.rest = RestAgent(self.symbol)

        if self.execution:
            self.funcs.append(run_execution_sim if self.backtesting else run_execution)

        self.funcs.append(run_logic_sim if self.backtesting else run_logic)
        self.funcs.append(run_parsing_sim if self.backtesting else run_parsing)
        self.funcs.append((run_wss_sim if self.backtesting else run_wss))

    def init_trade_param(self) -> None:
        self.ts: str = self.rest.get_tick_size()
        self.ls: str = self.rest.get_lot_size()
        self.trade_par[2] = self.pricePrec = (
            len(self.ts.split(sep=".")[-1]) if "." in self.ts else 0
        )
        self.trade_par[3] = self.qtyPrec = (
            len(self.ls.split(sep=".")[-1]) if "." in self.ls else 0
        )
        self.priceMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.trade_par[0] = round(float(self.ts) * self.priceMult)
        self.trade_par[1] = round(float(self.ls) * self.qtyMult)

    def get_kwargs_for_func(self, func: FunctionType) -> dict | None:
        sig = inspect.signature(func)
        proc_id = len(self.procs)
        task_id = proc_id + 10
        proc_name = func.__name__.removeprefix("run_").upper()
        kwargs = {}
        for param_name in sig.parameters:
            if hasattr(self, param_name):
                val = getattr(self, param_name)
                kwargs[param_name] = val
            elif param_name == "kwargs":
                kwargs["proc_id"], kwargs["task_id"] = proc_id, task_id
                kwargs["sc_sem"] = self.sc_sem
            else:
                logger.error(f"Missing arg: [{param_name}] for [{proc_name}]")
                return None

        kwargs = self.baseKwargs | kwargs
        self.procs[proc_id] = {"proc_name": proc_name, "task_id": task_id}
        return kwargs

    def run_proc(self, func) -> bool:
        kwargs = self.get_kwargs_for_func(func)
        if isinstance(kwargs, dict):
            name: str = self.procs[kwargs["proc_id"]]["proc_name"]
            p = Process(
                target=func,
                kwargs=kwargs,
                name=name,
                daemon=True,
            )
            p.start()
            self.procs[kwargs["proc_id"]]["proc"] = p
            logger.success(f"-- Core -- | Process [{name}: pid[{p.pid}]], started.")
            return True

        else:
            logger.warning("-- Core -- | RunProc | kwargs is not dict")
            return False

    def run_core_engine(self) -> None:
        logger.info("-- Core -- | Started, init...")
        try:
            self.check_dirs()
            self.check_data()
            self.init_funcs()
            self.init_trade_param()

            for func in self.funcs:
                if self.run_proc(func=func) is False:
                    return

            logger.info("-- Core -- | Init completed.")

            self.manager.run(procs=self.procs, scs_sem=self.sc_sem)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("-- Core -- | Close the Core.")


@manager_office(main=True)
def run_core(**kwargs) -> None:
    logger.remove()
    logger.add(
        CORE_LOG_PATH,
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )
    state = RunMain(**kwargs)
    state.run_core_engine()
