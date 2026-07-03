import os
import time
import traceback
from collections import deque
from datetime import date
from multiprocessing.synchronize import Event
from threading import Lock, Thread

from msgspec.json import Encoder

from ....constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH
from ....utils.handlers import error_handler
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_wss import Wss
from ...base.utils.data_structs import AggTradeSim


class DataPrepper:
    def __init__(
        self, symbol: str, startDate: str | None, endDate: str | None, lock: Lock
    ) -> None:
        self.symbol: str = symbol.upper()
        self.startDate, self.endDate = startDate, endDate
        self.lock = lock

        self.datadir: str = DATA_PATH
        self.typeData: str = DATA_TYPE_AGGTRADES_PATH
        self.base_path: str = f"{self.datadir}/{self.typeData}/{self.symbol}"

        self.encoder: Encoder = Encoder()
        self.queue: deque[AggTradeSim] = deque(maxlen=10000)

        self.is_running, self.complete = True, False
        self.error: None | str = None

    def start(self) -> None:
        self.subP: Thread = Thread(target=self.run_prepper_engine, daemon=True)
        self.subP.start()

    def run_prepper_engine(self) -> None:
        try:
            data_paths: list[str] = self.get_data_paths()
            for path in data_paths:
                with open(file=path, mode="r") as f:
                    next(f)
                    for line in f:
                        if not self.is_running:
                            break

                        while len(self.queue) == self.queue.maxlen:
                            self.lock.acquire()

                        data: list[str] = line.strip().split(sep=",")
                        obj = AggTradeSim(
                            e=self.typeData,
                            E=int(data[5]),
                            a=int(data[0]),
                            s=self.symbol,
                            p=data[1],
                            q=data[2],
                            f=int(data[3]),
                            l=int(data[4]),
                            T=int(data[5]),
                            m=(data[6] in ("true", "True")),
                        )
                        self.queue.append(obj)

            self.complete = True

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.is_running = False

    def get_data_paths(self) -> list[str]:
        paths: list[str] = [p for p in os.listdir(self.base_path) if p.endswith(".csv")]
        dates: list[date] = sorted([date.fromisoformat(p.split(".")[0]) for p in paths])
        startDate: date = (
            dates[0] if (self.startDate is None) else date.fromisoformat(self.startDate)
        )
        endDate: date = (
            dates[-1] if (self.endDate is None) else date.fromisoformat(self.endDate)
        )
        needDates: list[date] = [d for d in dates if (startDate <= d <= endDate)]
        return [f"{self.base_path}/{date.isoformat(d)}.csv" for d in needDates]


class WssSimAgent(Wss):
    def __init__(self, manager: AgentManager, parsing_event: Event) -> None:
        super().__init__(manager=manager)
        self.parsing_event = parsing_event

        cfgBT = manager.cfgBacktesting
        self.ottrade, self.nttrade = 0, 0
        self.encoder = Encoder()
        self.lock = Lock()
        self.prepper = DataPrepper(
            symbol=manager.symbol,
            startDate=cfgBT.startDateForPrepper,
            endDate=cfgBT.endDateForPrepper,
            lock=self.lock,
        )
        self.prepper.start()

    @error_handler(set_status_code=True)
    def run_wss_sim_engine(self) -> None:
        # Local Links
        prepper, parsing_event = self.prepper, self.parsing_event
        proc_status, task_status = self.proc_status, self.task_status
        raw_buf = self.manager.raw_buf
        wCellC, rCellC = self.wCellC, self.rCellC
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount, safe_lag = self.cell_amount, self.safe_lag
        encode_data = self.encode_data
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

                        if self.lock.locked():
                            self.lock.release()

                        time.sleep(0)

                    if prepper.queue:
                        raw_data: bytes = encode_data(prepper.queue)
                        alarm_clock(wCellC, rCellC, cell_amount, safe_lag)
                        time.sleep(self.time_to_sleep())
                        if set_raw_data(
                            raw_data=raw_data,
                            raw_buf=raw_buf,
                            wCellC=wCellC,
                            cell_amount=cell_amount,
                            data_size=data_size,
                            data_offset=data_offset,
                            dataHeader_offset=dataHeader_offset,
                        ):
                            if parsing_event.is_set() is False:
                                parsing_event.set()
                else:
                    raise RuntimeError(prepper.error)

    def time_to_sleep(self) -> float:
        # ott: Old Time Trade | ntt: New Time Trade
        ott, ntt = self.ottrade, self.nttrade
        # - - -
        if 0 < ott:
            if ott <= ntt:
                if ott < ntt:
                    self.ottrade = ntt
                return (ntt - ott) / 1000  # Time To Sleep
        else:
            self.ottrade = ntt

        return 0  # Base Time To Sleep

    def encode_data(self, queue: deque[AggTradeSim]) -> bytes:
        data = queue.popleft()
        self.nttrade = data.T
        return self.encoder.encode(data)

    def complete(self) -> bool:
        return self.prepper.complete and (not self.prepper.queue)


@manager_office()
def run_wss_sim_v2(parsing_event: Event, **kwargs) -> None:
    agent = WssSimAgent(kwargs["manager"], parsing_event)
    agent.run_wss_sim_engine()
