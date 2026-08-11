from abc import ABC, abstractmethod

from ...footprint import BaseFootprintReader
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler


class Base(ABC):
    def __init__(self, manager: NodeManager, reader: BaseFootprintReader) -> None:
        self.manager: NodeManager = manager
        self.reader: BaseFootprintReader = reader

        self.set_proc_sc = manager.set_proc_sc
        self.have_status = manager.have_status
        self.task_status = manager.task_status
        self.check_base_task = manager.check_base_task

        cfgMetrics = manager.cfgMetrics
        self.parsing_complete: memoryview = cfgMetrics.parsing_complete
        self.logic_complete: memoryview = cfgMetrics.logic_complete

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        flag = self.reader._spare_flags
        # - - -
        while True:
            init_session, self.pass_lag, self.pass_lag_limit = False, 0, 3
            while True:
                if self.have_status():
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if self.task_status[0] & scs.COMPLETE:
                                self.final_actions()
                                self.set_proc_sc(scs.COMPLETE, wait_main_task=False)

                            return

                    elif task & scs.FP_RE_INIT:
                        break

                if (flag[0] == 0) and (self.parsing_complete[0] == 0):
                    self.alarm_clock()

                if flag[0] == 1:
                    if init_session is False:
                        self.reader._init_session()
                        init_session = True

                    self.reader._update_states()
                    self.check_lag()
                    self.post_update()
                    flag[0] = 0

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
