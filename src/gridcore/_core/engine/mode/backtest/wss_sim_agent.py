"""Simulated WebSocket agent streaming prepped CSV tick data."""

import struct
import time
from collections import deque

from ....settings import StatusCodes as scs
from ....utils.handlers import error_handler, supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_data_prepper import BaseDataPrepper
from ...base.base_wss import Wss


class DataPrepper(BaseDataPrepper):
    """Threaded queue container packing CSV tick rows into binary stream payloads."""

    def __init__(self, symbol: str, start_date: str, end_date: str) -> None:
        super().__init__(symbol, start_date, end_date)

        self.queue: deque = deque(maxlen=10000)

    def alarm_clock(self) -> None:
        """Throttles reader when output queue reaches capacity limit."""

        while len(self.queue) == self.queue.maxlen:
            time.sleep(0)

    def prepper_data(self, data: bytes) -> None:
        """Packs CSV fields into packed binary struct payload `@ddq?`."""

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
    """Simulated Wss process pushing packed tick binary payloads into DataStream ring buffer."""

    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        self.prepper = DataPrepper(
            symbol=manager.cfgCoin.symbol,
            start_date=manager.cfgSetup.backtest_start_date,
            end_date=manager.cfgSetup.backtest_end_date,
        )
        self.prepper.start()

    @error_handler(set_status_code=True)
    def run_wss_engine(self) -> None:
        """Main process loop streaming prepped tick data into DataStream ring buffer cells."""

        # Local Links
        prepper = self.prepper
        proc_status, task_status = self.proc_status, self.task_status
        wid, rid = self.ds_wid, self.ds_rid
        data, data_size = self.ds_data, self.ds_data_size
        data_header = self.ds_data_header
        cell_amount, safe_lag = self.ds_cell_amount, self.ds_safe_lag
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

                    alarm_clock(wid, rid, cell_amount, safe_lag)

                    if prepper.queue:
                        raw_data: bytes = prepper.queue.popleft()
                        set_raw_data(
                            raw_data=raw_data,
                            writer_id=wid,
                            data=data,
                            data_header=data_header,
                            data_size=data_size,
                            cell_amount=cell_amount,
                        )
                else:
                    raise RuntimeError(prepper.error)

    def complete(self) -> bool:
        """Checks if input tick file has been completely ingested and queue is drained."""

        return self.prepper.complete and (not self.prepper.queue)


@supervisor()
def run_wss_sim(**kwargs) -> None:
    """Supervisor-wrapped entry point for simulated Wss process."""

    agent = WssSimAgent(manager=kwargs["manager"])
    agent.run_wss_engine()
