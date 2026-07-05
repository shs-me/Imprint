import time

from ....utils.handlers import error_handler
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_wss import Wss
from ...base.utils.data_prepper import DataPrepper


class WssSimAgent(Wss):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        cfgBT = manager.cfgBacktesting
        self.prepper = DataPrepper(
            symbol=manager.symbol,
            startDate=cfgBT.startDateForPrepper,
            endDate=cfgBT.endDateForPrepper,
        )
        self.prepper.start()

    @error_handler(set_status_code=True)
    def run_wss_sim_engine(self) -> None:
        # Local Links
        prepper = self.prepper
        proc_status, task_status = self.proc_status, self.task_status
        raw_buf = self.manager.raw_buf
        wCellC, rCellC = self.wCellC, self.rCellC
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount, safe_lag = self.cell_amount, self.safe_lag
        set_raw_data, alarm_clock = self.set_raw_data, self.alarm_clock
        # - - -
        while True:
            # - - -
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions()
                            return

                if prepper.error is None:
                    if not prepper.queue:
                        if prepper.complete:
                            self.set_proc_sc(code=scs.DATA_PREPPERED)

                        time.sleep(0)
                        continue

                    alarm_clock(wCellC, rCellC, cell_amount, safe_lag)

                    if prepper.queue:
                        raw_data: bytes = prepper.queue.popleft()
                        set_raw_data(
                            raw_data=raw_data,
                            raw_buf=raw_buf,
                            wCellC=wCellC,
                            cell_amount=cell_amount,
                            data_size=data_size,
                            data_offset=data_offset,
                            dataHeader_offset=dataHeader_offset,
                        )
                else:
                    raise RuntimeError(prepper.error)

    def complete(self) -> bool:
        return self.prepper.complete and (not self.prepper.queue)


@manager_office()
def run_wss_sim(**kwargs) -> None:
    agent = WssSimAgent(manager=kwargs["manager"])
    agent.run_wss_sim_engine()
