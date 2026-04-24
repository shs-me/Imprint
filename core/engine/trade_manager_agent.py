import gc
from multiprocessing.synchronize import Event
from types import MethodType

from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as sc


class TradeManagerAgent:
    def __init__(self, manager: AgentManager) -> None:
        self.manager: AgentManager = manager
        self.set_proc_sc = manager.set_proc_sc
        self.check_task = manager.check_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

    def run_trade_manager_engine(self) -> None:
        task_status, proc_status = self.task_status, self.proc_status
        verifed_sc = 0
        while True:
            gc.collect()
            while True:
                if proc_status[0] == 0 and task_status[0] == 0:
                    pass
                else:
                    if task := self.check_task(complete=True):
                        return


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = TradeManagerAgent(manager=kwargs["manager"])
    agent.run_trade_manager_engine()
