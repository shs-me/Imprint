import inspect
import os
from multiprocessing import Event, Lock, Process, Semaphore
from multiprocessing.synchronize import Event as EventT
from multiprocessing.synchronize import Lock as LockT
from multiprocessing.synchronize import Semaphore as SemT
from types import FunctionType

from loguru import logger

from core.constant import CORE_LOG_PATH, DIRS_LIST
from core.engine.agents.execution_agent import run_execution
from core.engine.agents.logic_agent import run_logic
from core.engine.agents.parsing_agent import run_parsing
from core.engine.agents.rest_agent import RestAgent
from core.engine.agents.wss_agent import run_wss
from core.engine.agents.wss_sim_agent import run_wss_sim
from core.settings import BacktestingMode, CoreResources
from core.utils.monitoring.main_manager import MainManager
from core.utils.monitoring.office import manager_office


class RunMain(CoreResources):
    def __init__(self, **kwargs) -> None:
        self.baseKwargs: dict = kwargs
        self.symbol: str = kwargs["symbol"]
        self.backtesting: bool = kwargs["backtesting"]
        self.manager: MainManager = kwargs.pop("manager")

        self.cfgBacktesting = self.manager.cfgBacktesting
        # CoreResources
        self.general_event: EventT = Event()
        self.execution_event: EventT = Event()
        self.parsing_event: EventT = Event()
        self.sc_sem: SemT = Semaphore(0)
        self.logic_lock: LockT = Lock()
        self.logic_lock.acquire(block=False)
        # Variable's
        self.procs: dict = {}
        self.rest = RestAgent(
            symbol=self.symbol,
            backtesting=self.backtesting,
            cfgBacktesting=self.cfgBacktesting,
        )
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""

    def _init_session(self) -> None:
        for _dir in DIRS_LIST:
            if not os.path.exists(_dir):
                os.mkdir(_dir)

        self.funcs = [
            run_logic,
            run_parsing,
            run_execution,
            run_wss_sim if self.backtesting else run_wss,
        ]

        self.ts = self.rest.get_tick_size()
        self.ls = self.rest.get_lot_size()
        self.trade_par[2] = self.pricePrec = (
            len(self.ts.split(sep=".")[-1]) if "." in self.ts else 0
        )
        self.trade_par[3] = self.qtyPrec = (
            len(self.ls.split(sep=".")[-1]) if "." in self.ls else 0
        )
        self.priceMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.trade_par[0] = round(float(self.ts) * self.priceMult)
        self.trade_par[1] = round(float(self.ls) * self.qtyMult)

    def _get_kwargs_for_func(self, func: FunctionType) -> dict | None:
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

    def _run_proc(self, func) -> bool:
        kwargs = self._get_kwargs_for_func(func)
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
        self._init_session()
        for func in self.funcs:
            if self._run_proc(func=func) is False:
                return

        logger.info("-- Core -- | Init completed.")
        try:
            self.manager.run(
                procs=self.procs,
                general_event=self.general_event,
                scs_sem=self.sc_sem,
            )
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("-- Core -- | Close the Core.")


@manager_office(main=True)
def run_core(
    backtesting: bool = False,
    mode: BacktestingMode = BacktestingMode.REAL_TIME_SIM,
    symbol: str = "DASHUSDT",
    **kwargs,
) -> None:
    logger.remove()
    logger.add(
        CORE_LOG_PATH,
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    kwargs["backtesting"] = backtesting
    kwargs["mode"] = mode
    kwargs["symbol"] = symbol

    state = RunMain(**kwargs)
    state.run_core_engine()
