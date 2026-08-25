import struct
import time
from collections import deque

from numpy import int64
from numpy.typing import NDArray

from ....ipc import NodeManager
from ....settings import StatusCodes as scs
from ....utils.handlers import error_handler
from ...utils.base_data_prepper import BaseDataPrepper
from ..base import Base


class DataPrepper(BaseDataPrepper):
    def __init__(self, symbol: str, start_date: str, end_date: str) -> None:
        super().__init__(symbol, start_date, end_date)

        self.queue: deque = deque(maxlen=10000)

    def alarm_clock(self) -> None:
        while len(self.queue) == self.queue.maxlen:
            time.sleep(0)

    def prepper_data(self, line: NDArray[int64]) -> None:
        self.queue.append(struct.pack("@qqqq", line[0], line[1], line[2], line[3]))

    def post_prepper(self) -> None:
        pass


class Backtest(Base):
    def __init__(self, manager: NodeManager) -> None:
        super().__init__(manager=manager)

        self.prepper = DataPrepper(
            symbol=manager.cfgCoin.symbol,
            start_date=manager.cfgSetup.backtest_start_date,
            end_date=manager.cfgSetup.backtest_end_date,
        )
        self.prepper.start()

    @error_handler(set_status_code=True)
    def run_wss_engine(self) -> None:
        # Local Links
        prepper = self.prepper
        have_status, task_status = self.have_status, self.task_status
        wid, rid = self.ds_wid, self.ds_rid
        data, data_size = self.ds_data, self.ds_data_size
        data_header = self.ds_data_header
        cell_amount, safe_lag = self.ds_cell_amount, self.ds_safe_lag
        set_raw_data, alarm_clock = self.set_raw_data, self.alarm_clock
        # - - -
        while True:
            # - - -
            while True:
                if have_status():
                    task: int = self.check_base_task()
                    if task & scs.EXIT:
                        return self.set_proc_sc(scs.EXIT, wait_main_task=False)

                    if task & scs.COMPLETE:
                        if self.complete():
                            self.final_actions()
                            return self.set_proc_sc(scs.COMPLETE, wait_main_task=False)

                if prepper.error is None:
                    if not prepper.queue:
                        if prepper.complete:
                            self.set_proc_sc(
                                code=scs.DATA_PREPPERED, wait_main_task=True
                            )

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
        return self.prepper.complete and (not self.prepper.queue)
