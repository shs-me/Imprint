import importlib
import inspect
from abc import ABC, abstractmethod

from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from ...utils.monitoring.status_codes import StatusCodes as scs
from .base_footprint_reader import BaseFootprintReader, FootprintReader
from .base_sync import Sync


class Logic(ABC):
    def __init__(self, manager: AgentManager, reader: FootprintReader) -> None:
        self.manager: AgentManager = manager
        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status, self.proc_status = manager.task_status, manager.proc_status

        self.reader: FootprintReader = reader

        cfgMetrics = manager.cfgMetrics
        self.parsing_complete: memoryview = cfgMetrics.parsing_complete
        self.logic_complete: memoryview = cfgMetrics.logic_complete

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        reader, spareFlag = self.reader, self.reader._spare_flag
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
                                self.set_proc_sc(scs.COMPLETE)

                            return

                    elif task & scs.FP_RE_INIT:
                        break

                alarm_clock()

                if spareFlag[0] == 1:
                    if init_session is False:
                        reader._init_session()
                        init_session = True

                    reader._update_states()
                    self.check_lag()
                    self.post_update()
                    spareFlag[0] = 0

    def complete(self) -> bool:
        return self.parsing_complete[0] == 1

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
        self.logic_complete[0] = 1
        self.post_final_action()
        self.reader._final_actions()

    @abstractmethod
    def post_final_action(self) -> None:
        pass


def resolve_reader(manager: AgentManager, sync: Sync) -> FootprintReader:
    module = importlib.import_module(manager.cfgFootprint.algorithm_module)
    reader: type[FootprintReader] = BaseFootprintReader
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if (name == manager.cfgFootprint.algorithm_class_name) and issubclass(
            obj, FootprintReader
        ):
            reader = obj

    return reader(manager, sync)
