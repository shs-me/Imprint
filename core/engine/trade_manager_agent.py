import gc
from multiprocessing.synchronize import Event

from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as sc


class TradeManagerAgent:
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager

        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem

    def run_trade_manager_engine(self) -> None:
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        set_status, have_problem = self.set_status, self.have_problem
        have_task = self.have_task
        while True:
            gc.collect()
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        break
                    set_status(code=WAKE_UP)
                    # - - -

                else:
                    return


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = TradeManagerAgent(manager=kwargs["manager"])
    agent.run_trade_manager_engine()
