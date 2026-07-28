"""Analysis process engine loop and dynamic algorithm loader."""

import importlib
import inspect
from abc import ABC, abstractmethod

from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from .base_footprint_reader import BaseFootprintReader, FootprintReader
from .base_sync import Sync


class Logic(ABC):
    """Base class orchestrating strategy processing steps upon shared memory updates."""

    def __init__(self, manager: AgentManager, reader: FootprintReader) -> None:
        """Binds metrics buffers, process task references, and active FootprintReader instance."""

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
        """Main process loop evaluating strategy logic upon shared memory flag updates."""

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
        """Checks if upstream parsing engine has completed tick ingestion."""

        return self.parsing_complete[0] == 1

    @abstractmethod
    def alarm_clock(self) -> None:
        """Abstract idle wait hook invoked while waiting for new shared memory frame updates."""

        pass

    @abstractmethod
    def check_lag(self) -> None:
        """Abstract latency monitoring hook invoked during each state evaluation cycle."""

        pass

    @abstractmethod
    def post_update(self) -> None:
        """Abstract hook invoked immediately after strategy pattern evaluation completes."""

        pass

    def final_actions(self) -> None:
        """Sets completion flags and triggers strategy finalization callbacks."""

        self.logic_complete[0] = 1
        self.post_final_action()
        self.reader._final_actions()

    @abstractmethod
    def post_final_action(self) -> None:
        """Abstract teardown hook invoked upon strategy engine termination."""

        pass


def resolve_reader(manager: AgentManager, sync: Sync) -> FootprintReader:
    """Dynamically loads and instantiates target user strategy class from specified module path.

    Returns:
        FootprintReader: Configured user strategy reader instance.
    """

    module = importlib.import_module(manager.cfgFootprint.algorithm_module)
    reader: type[FootprintReader] = BaseFootprintReader
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if (name == manager.cfgFootprint.algorithm_class_name) and issubclass(
            obj, FootprintReader
        ):
            reader = obj

    return reader(manager, sync)
