import importlib.util
import inspect
import os
from abc import ABC, abstractmethod

from ...constant import ALGORITHM_PATH
from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from ...utils.monitoring.status_codes import StatusCodes as scs
from .base_footprint_reader import BaseFootprintReader, FootprintReader
from .base_sync import Sync


class Logic(ABC):
    def __init__(self, manager: AgentManager, reader: FootprintReader) -> None:
        self.manager: AgentManager = manager
        self.reader: FootprintReader = reader

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status, self.proc_status = manager.task_status, manager.proc_status

        cfgBT = manager.cfgBacktesting
        self.execution_sim = cfgBT.execution_sim

        cfgMetrics = manager.cfgMetrics
        self.tradesParsed: memoryview = manager.metrics_buf[
            cfgMetrics.tradesParsed : cfgMetrics.tradesParsed + 1
        ]
        self.footprintReaded: memoryview = manager.metrics_buf[
            cfgMetrics.footprintReaded : cfgMetrics.footprintReaded + 1
        ]

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        reader, spareFlag = self.reader, self.reader.spare_flag
        proc_status, task_status = self.proc_status, self.task_status
        alarm_clock = self.alarm_clock
        # - - -
        while True:
            init_session, self.pass_lag, self.pass_lag_limit = False, 0, 3
            while True:
                if (proc_status[0] != 0) or (task_status[0] != 0):
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions()
                            return

                    elif task & scs.FP_RE_INIT:
                        break

                alarm_clock()

                if spareFlag[0] == 1:
                    if init_session is False:
                        init_session = reader.init_session()

                    reader.update_states()
                    self.check_lag()
                    self.post_update()
                    spareFlag[0] = 0

    def complete(self) -> bool:
        return self.tradesParsed[0] == 1

    @abstractmethod
    def alarm_clock(self) -> None:
        pass

    @abstractmethod
    def check_lag(self) -> None:
        pass

    @abstractmethod
    def post_update(self) -> None:
        pass

    def final_actions(self) -> None:
        self.footprintReaded[0] = 1
        self.post_final_action()
        self.reader.final_actions()
        self.set_proc_sc(scs.COMPLETE)

    @abstractmethod
    def post_final_action(self) -> None:
        pass


def resolve_reader(manager: AgentManager, sync: Sync) -> FootprintReader:
    paths: list[str] = []
    for p in os.listdir(ALGORITHM_PATH):
        if p.endswith(".py"):
            paths.append(f"{ALGORITHM_PATH}/{p}")

    obj = BaseFootprintReader
    for path in paths:
        result = get_plugin(path=path)
        if result:
            obj = result

    reader = obj(manager=manager, sync=sync)
    return reader


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
