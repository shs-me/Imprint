import importlib.util
import inspect
import os
import time
from multiprocessing.synchronize import Event

from core.constant import ALGORITHM_PATH
from core.engine.agents_utils.logic.example import BaseFootprintReader
from core.engine.agents_utils.logic.footprint_reader import FootprintReader
from core.settings import BacktestingMode as bm
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as scs


class LogicAgent:
    def __init__(
        self,
        manager: AgentManager,
        reader: FootprintReader,
        is_base_reader: bool,
        pre_sleep_logic: Event,
        general_event: Event,
    ) -> None:
        self.manager: AgentManager = manager
        self.reader: FootprintReader = reader
        self.is_base_reader: bool = is_base_reader
        self.pre_sleep_logic: Event = pre_sleep_logic
        self.wait_main: Event = general_event

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

        self.backtesting: bool = manager.backtesting
        self.btMode: bm = manager.mode
        self.is_real: bool = self.btMode == bm.REAL_TIME_SIM
        self.is_zero_sleep: bool = self.btMode == bm.ZERO_SLEEP
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.tradesParsed: memoryview = self.manager.metrics_buf[
            slice(*self.cfgMetrics.tradesParsed)
        ]
        # Footprint
        self.cfgFP = self.manager.cfgFootprint
        self._space_read: memoryview = self.manager.footprint_buf[
            self.cfgFP.space_read : self.cfgFP.space_read + 1
        ]

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        reader, flag = self.reader, self.reader.spare_flag
        tradesParsed = self.tradesParsed
        pre_sleep_logic, alarm_clock = self.pre_sleep_logic, self._alarm_clock
        # - - -
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        while True:
            is_real: bool = self.is_real
            pass_lag_limit: int = 3
            pass_lag: int = 0
            init_session: bool = False
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions(is_real)

                            return

                    elif task & scs.FP_RE_INIT:
                        break

                alarm_clock(flag, tradesParsed, pre_sleep_logic)
                if flag[0] == 1:
                    if init_session is False:
                        init_session = reader.init_session()

                    reader.update_states()
                    if is_real:
                        pre_sleep_logic.clear()
                        if reader.lag_is_safe() is False:
                            pass_lag += 1
                            if pass_lag >= pass_lag_limit:
                                self.set_proc_sc(scs.ANALYSIS_LAG_MORE_SAFE_LAG)

                    if self.backtesting:
                        self._space_read[0] = 1
                        if is_real:
                            if self.reader.execution_event.is_set() is False:
                                self.reader.execution_event.set()

                        while self._space_read[0] == 1:
                            if task_status[0] == 0:
                                if self.is_zero_sleep:
                                    time.sleep(0)
                            else:
                                break

                    flag[0] = 0

    def complete(self) -> bool:
        return self.tradesParsed[0] == 1

    def final_actions(self, is_real: bool) -> None:
        if self.backtesting and is_real:
            if self.reader.execution_event.is_set() is False:
                self.reader.execution_event.set()

        self.reader.final_actions()
        self.set_proc_sc(scs.COMPLETE)

    def _alarm_clock(
        self, flag: memoryview, tradesParsed: memoryview, pre_sleep_logic: Event
    ) -> None:
        if not self.is_real:
            while flag[0] == 0 and tradesParsed[0] == 0:
                if self.task_status[0] == 0:
                    if self.is_zero_sleep:
                        time.sleep(0)
                else:
                    return
        else:
            if (flag[0] == 0) and (tradesParsed[0] == 0):
                pre_sleep_logic.wait()


def resolve_reader(
    manager: AgentManager, execution_event: Event
) -> tuple[FootprintReader, bool]:
    paths: list[str] = []
    for p in os.listdir(ALGORITHM_PATH):
        if p.endswith(".py"):
            paths.append(f"{ALGORITHM_PATH}/{p}")

    obj, is_base_reader = BaseFootprintReader, True
    for path in paths:
        result = get_plugin(path=path)
        if result:
            obj, is_base_reader = result, False

    reader = obj(manager=manager, execution_event=execution_event)
    return reader, is_base_reader


@error_handler()
def get_plugin(path: str) -> None | type[FootprintReader]:
    module_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, FootprintReader):
                if obj is not FootprintReader:
                    return obj


@manager_office()
def run_logic(
    logic_event: Event,
    execution_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    reader, is_base_reader = resolve_reader(kwargs["manager"], execution_event)
    agent = LogicAgent(
        kwargs["manager"],
        reader=reader,
        is_base_reader=is_base_reader,
        pre_sleep_logic=logic_event,
        general_event=general_event,
    )
    agent.run_logic_engine()
