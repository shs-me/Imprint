import struct
import time
from collections import deque

from ....utils.handlers import error_handler
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_data_prepper import BaseDataPrepper
from ...base.base_wss import Wss


class DataPrepper(BaseDataPrepper):
    def __init__(self, symbol: str, start_date: str, end_date: str) -> None:
        super().__init__(symbol, start_date, end_date)

        self.queue: deque = deque(maxlen=10000)

    def alarm_clock(self) -> None:
        while len(self.queue) == self.queue.maxlen:
            time.sleep(0)

    def prepper_data(self, data: bytes) -> None:
        list_data: list[bytes] = data.split(b",")
        self.queue.append(
            struct.pack(
                "@ddq?",
                float(list_data[1]),
                float(list_data[2]),
                int(list_data[5]),
                b"true" in list_data[6],
            )
        )

    def post_prepper(self) -> None:
        pass


class WssSimAgent(Wss):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        cfgBT = manager.cfgBacktesting
        self.prepper = DataPrepper(
            symbol=manager.cfgCoin.symbol,
            start_date=cfgBT.backtest_start_date,
            end_date=cfgBT.backtest_end_date,
        )
        self.prepper.start()

    @error_handler(set_status_code=True)
    def run_wss_sim_engine(self) -> None:
        # Local Links
        prepper = self.prepper
        proc_status, task_status = self.proc_status, self.task_status
        wCellC, rCellC = self.wCellC, self.rCellC
        data, data_size = self.data, self.data_size
        data_header = self.data_header
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
                            data=data,
                            data_header=data_header,
                            wCellC=wCellC,
                            cell_amount=cell_amount,
                            data_size=data_size,
                        )
                else:
                    raise RuntimeError(prepper.error)

    def complete(self) -> bool:
        return self.prepper.complete and (not self.prepper.queue)


@manager_office()
def run_wss_sim(**kwargs) -> None:
    agent = WssSimAgent(manager=kwargs["manager"])
    agent.run_wss_sim_engine()
