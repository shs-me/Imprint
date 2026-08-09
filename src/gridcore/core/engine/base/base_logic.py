"""Analysis process engine loop and dynamic algorithm loader."""

from abc import ABC, abstractmethod

from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from .base_footprint_reader import FootprintReader


class Logic(ABC):
    """Base class orchestrating strategy processing steps upon shared memory updates."""

    def __init__(self, manager: AgentManager, reader: FootprintReader) -> None:
        """Binds metrics buffers, process task references, and active FootprintReader instance."""

        self.manager: AgentManager = manager
        self.reader: FootprintReader = reader

        self.set_proc_sc = manager.set_proc_sc
        self.have_status = manager.have_status
        self.task_status = manager.task_status
        self.check_base_task = manager.check_base_task

        cfgMetrics = manager.cfgMetrics
        self.parsing_complete: memoryview = cfgMetrics.parsing_complete
        self.logic_complete: memoryview = cfgMetrics.logic_complete

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        """Main process loop evaluating strategy logic upon shared memory flag updates."""

        # LocalLinks
        reader, spare_flags = self.reader, self.reader._spare_flags
        have_status, task_status = self.have_status, self.task_status
        alarm_clock = self.alarm_clock
        # - - -
        while True:
            init_session, self.pass_lag, self.pass_lag_limit = False, 0, 3
            while True:
                if have_status():
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions()
                                self.set_proc_sc(scs.COMPLETE, wait_main_task=False)

                            return

                    elif task & scs.FP_RE_INIT:
                        break

                alarm_clock()

                if spare_flags[0] == 1:
                    if init_session is False:
                        reader._init_session()
                        init_session = True

                    reader._update_states()
                    self.check_lag()
                    self.post_update()
                    spare_flags[0] = 0

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
