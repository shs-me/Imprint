import struct
import time
from collections import deque
from dataclasses import dataclass, field
from typing import override

from numpy import int64
from numpy.typing import NDArray

from imprint.core.pipeline.streaming.base import Base
from imprint.core.pipeline.utils.base_data_prepare import BaseDataPrepare
from imprint.core.settings import StatusCodes as scs
from imprint.core.utils.handlers import error_handler


@dataclass(slots=True)
class DataPrepare(BaseDataPrepare):
    queue: deque[bytes] = field(
        default_factory=lambda: deque(maxlen=10000), init=False
    )

    @override
    def alarm_clock(self) -> None:
        while len(self.queue) == self.queue.maxlen:
            time.sleep(0)

    @override
    def prepare_data(self, line: NDArray[int64]) -> None:
        self.queue.append(
            struct.pack("@qqqq", line[0], line[1], line[2], line[3])
        )

    @override
    def post_prepare(self) -> None:
        pass


@dataclass(slots=True)
class MarketDataStream(Base):
    prepare: DataPrepare = field(init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.prepare = DataPrepare(
            symbol=self.manager.cfgCoin.symbol,
            start_date=self.manager.cfgSetup.backtest_start_date,
            end_date=self.manager.cfgSetup.backtest_end_date,
        )
        self.prepare.start()

    @error_handler(set_status_code=True)
    def run(self) -> None:
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
                    return self.manager.set_proc_sc(
                        scs.EXIT, wait_main_task=False
                    )

                if task & scs.COMPLETE and self.complete():
                    self.final_actions()
                    return self.manager.set_proc_sc(
                        scs.COMPLETE, wait_main_task=False
                    )

            if self.prepare.error is None:
                if not self.prepare.queue:
                    if self.prepare.complete:
                        self.manager.set_proc_sc(
                            code=scs.DATA_PREPPERED, wait_main_task=True
                        )

                    time.sleep(0)
                    continue

                while self.lag_not_is_safe(wid, rid, cell_amount, safe_lag):
                    time.sleep(0)

                if self.prepare.queue:
                    raw_data: bytes = self.prepare.queue.popleft()
                    self.set_raw_data(
                        raw_data=raw_data,
                        writer_id=wid,
                        data=data,
                        data_header=data_header,
                        data_size=data_size,
                        cell_amount=cell_amount,
                    )
            else:
                raise RuntimeError(self.prepare.error)

    def complete(self) -> bool:
        return self.prepare.complete and (not self.prepare.queue)
