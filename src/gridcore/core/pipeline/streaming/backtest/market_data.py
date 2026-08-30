import struct
import time
from collections import deque
from dataclasses import dataclass, field
from typing import override

from numpy import int64
from numpy.typing import NDArray

from ....settings import StatusCodes as scs
from ....utils.handlers import error_handler
from ...utils.base_data_prepper import BaseDataPrepper
from ..base import Base


@dataclass(slots=True)
class DataPrepper(BaseDataPrepper):
    queue: deque[bytes] = field(default_factory=lambda: deque(maxlen=10000), init=False)

    @override
    def alarm_clock(self) -> None:
        while len(self.queue) == self.queue.maxlen:
            time.sleep(0)

    @override
    def prepper_data(self, line: NDArray[int64]) -> None:
        self.queue.append(struct.pack("@qqqq", line[0], line[1], line[2], line[3]))

    @override
    def post_prepper(self) -> None:
        pass


@dataclass(slots=True)
class MarketDataStream(Base):
    prepper: DataPrepper = field(init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.prepper = DataPrepper(
            symbol=self.manager.cfgCoin.symbol,
            start_date=self.manager.cfgSetup.backtest_start_date,
            end_date=self.manager.cfgSetup.backtest_end_date,
        )
        self.prepper.start()

    @error_handler(set_status_code=True)
    def run_wss_engine(self) -> None:
        # Local Links
        wid, rid = self.ds_wid, self.ds_rid
        data, data_size = self.ds_data, self.ds_data_size
        data_header = self.ds_data_header
        cell_amount, safe_lag = self.ds_cell_amount, self.ds_safe_lag
        # - - -
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                if task & scs.COMPLETE:
                    if self.complete():
                        self.final_actions()
                        return self.manager.set_proc_sc(
                            scs.COMPLETE, wait_main_task=False
                        )

            if self.prepper.error is None:
                if not self.prepper.queue:
                    if self.prepper.complete:
                        self.manager.set_proc_sc(
                            code=scs.DATA_PREPPERED, wait_main_task=True
                        )

                    time.sleep(0)
                    continue

                while self.lag_not_is_safe(wid, rid, cell_amount, safe_lag):
                    time.sleep(0)

                if self.prepper.queue:
                    raw_data: bytes = self.prepper.queue.popleft()
                    self.set_raw_data(
                        raw_data=raw_data,
                        writer_id=wid,
                        data=data,
                        data_header=data_header,
                        data_size=data_size,
                        cell_amount=cell_amount,
                    )
            else:
                raise RuntimeError(self.prepper.error)

    def complete(self) -> bool:
        return self.prepper.complete and (not self.prepper.queue)
