import os
import time
import traceback
from collections import deque
from datetime import date
from multiprocessing.synchronize import Event
from threading import Lock, Thread

import msgspec
from msgspec.json import Encoder

from core.constant import DATA_PATH, DATA_TYPE_AGGTRADES_PATH
from core.settings import BacktestingMode as bm
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as scs


class AggTradeSim(msgspec.Struct):
    e: str  # Event name
    E: int  # Event time
    a: int  # Agg Trade id
    s: str  # Symbol
    p: str  # Price
    q: str  # Quantity
    f: int  # First trade id
    l: int  # Last trade id # noqa
    T: int  # Trade time
    m: bool  # Is buyer maker


class DataPrepper:
    def __init__(
        self,
        symbol: str,
        lock: Lock,
        mode: bm,
        startDateForPrepper: str | None,
        endDateForPrepper: str | None,
    ) -> None:
        self.symbol: str = symbol.upper()
        self.lock: Lock = lock
        self.mode: bm = mode
        self.startDFP: str | None = startDateForPrepper
        self.endDFP: str | None = endDateForPrepper

        self.datadir: str = DATA_PATH
        self.typeData: str = DATA_TYPE_AGGTRADES_PATH
        self.base_path: str = f"{self.datadir}/{self.typeData}/{self.symbol}"

        self.encoder: Encoder = Encoder()
        self.queue: deque = deque(maxlen=10000)

        self.is_running, self.complete = True, False
        self.error: None | str = None
        self.nttrade: int = 0

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
                            if self.mode == bm.NONE_STOP or self.mode == bm.ZERO_SLEEP:
                                time.sleep(0.001)
                            elif self.mode == bm.REAL_TIME_SIM:
                                self.lock.acquire()

                        data: list[str] = line.strip().split(sep=",")
                        obj: bytes = self.encoder.encode(
                            AggTradeSim(
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
                        )
                        self.ntt = int(data[5])
                        self.queue.append(obj)

            self.complete = True

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.is_running = False

    def get_data_paths(self) -> list[str]:
        paths: list[str] = [p for p in os.listdir(self.base_path) if p.endswith(".csv")]
        dates: list[date] = sorted([date.fromisoformat(p.split(".")[0]) for p in paths])
        startDate: date = (
            dates[0] if (self.startDFP is None) else date.fromisoformat(self.startDFP)
        )
        endDate: date = (
            dates[-1] if (self.endDFP is None) else date.fromisoformat(self.endDFP)
        )
        needDates: list[date] = [d for d in dates if (startDate <= d <= endDate)]
        return [f"{self.base_path}/{date.isoformat(d)}.csv" for d in needDates]


class WssSimAgent:
    def __init__(
        self, manager: AgentManager, wake_up_parser: Event, general_event: Event
    ) -> None:
        self.manager: AgentManager = manager
        self.wake_up_parser: Event = wake_up_parser
        self.wait_main: Event = general_event

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

        self.cfgBT = self.manager.cfgBacktesting
        self.mode: bm = manager.mode
        self.lock: Lock = Lock()
        self.prepper: DataPrepper = DataPrepper(
            symbol=self.manager.symbol,
            lock=self.lock,
            mode=self.mode,
            startDateForPrepper=self.cfgBT.startDateForPrepper,
            endDateForPrepper=self.cfgBT.endDateForPrepper,
        )

        self.ottrade: int = 0  # new time trade
        self.min_delta: int = 0
        # InitGetRawData
        self.cfgRaw = self.manager.cfgRaw
        self.data_size: int = self.cfgRaw.data_size
        self.header_size: int = self.cfgRaw.header_size
        self.data_offset: int = self.cfgRaw.data[0]
        self.dataHeader_offset: int = self.cfgRaw.dataHeader[0]
        self.cell_amount: int = self.cfgRaw.cell_amount
        self.safe_lag: int = self.cfgRaw.safe_lag
        self.WriterCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.WriterCellCounter)
        ].cast("q")
        self.ReaderCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.ReaderCellCounter)
        ].cast("q")

    @error_handler(set_status_code=True)
    def run_wss_sim_engine(self) -> None:
        # Local Links
        prepper = self.prepper
        wake_up_parser = self.wake_up_parser
        # - - -
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        raw_buf = self.manager.raw_buf
        WCellC, RCellC = self.WriterCellCounter, self.ReaderCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount, safe_lag = self.cell_amount, self.safe_lag
        # - - -
        update_cells = self._update_cells
        alarm_clock = self._alarm_clock
        # - - -
        prepper.start()
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
                        continue

                    alarm_clock(
                        WCellC=WCellC,
                        RCellC=RCellC,
                        cell_amount=cell_amount,
                        safe_lag=safe_lag,
                    )
                    if update_cells(
                        queue=prepper.queue,
                        raw_buf=raw_buf,
                        WCellC=WCellC,
                        cell_amount=cell_amount,
                        data_size=data_size,
                        data_offset=data_offset,
                        dataHeader_offset=dataHeader_offset,
                    ):
                        if wake_up_parser.is_set() is False:
                            wake_up_parser.set()
                    else:
                        raise RuntimeError(prepper.error)
                else:
                    return

    def complete(self) -> bool:
        return self.prepper.complete and not self.prepper.queue

    def final_actions(self) -> None:
        self.set_proc_sc(scs.COMPLETE)

    def _alarm_clock(
        self,
        WCellC: memoryview,
        RCellC: memoryview,
        cell_amount: int,
        safe_lag: int,
    ) -> None:
        if self.mode == bm.ZERO_SLEEP or self.mode == bm.NONE_STOP:
            while ((WCellC[0] - RCellC[0] + cell_amount) % cell_amount) > safe_lag:
                if self.mode == bm.ZERO_SLEEP:
                    time.sleep(0)

        elif self.mode == bm.REAL_TIME_SIM:
            if ((WCellC[0] - RCellC[0] + cell_amount) % cell_amount) > safe_lag:
                writer_cell = WCellC[0]  # debug
                reader_cell = RCellC[0]  # debug
                lag = (writer_cell - reader_cell + cell_amount) % cell_amount  # debug
                raise RuntimeError(
                    f"WssAgentSim: AlarmClock: reading lag[{lag}] > safe lag[{safe_lag}]"
                )

            time.sleep(self._time_to_sleep())

    def _time_to_sleep(self) -> float:
        # ott: Old Time Trade | ntt: New Time Trade
        ott, ntt = self.ottrade, self.prepper.nttrade
        # - - -
        if 0 < ott:
            if ott <= ntt:
                if ott < ntt:
                    self.ottrade = ntt

                return (ntt - ott) / 1000  # Time To Sleep

        else:
            self.ottrade = ntt

        return 0  # Base Time To Sleep

    def _update_cells(
        self,
        queue: deque[bytes],
        raw_buf: memoryview,
        WCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
    ) -> bool:
        raw_data: bytes = queue.popleft()
        if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
            cell: int = WCellC[0]

            raw_buf[cell + dataHeader_offset] = lrd
            start: int = cell * data_size + data_offset
            raw_buf[start : start + lrd] = raw_data

            new_cell = cell + 1
            WCellC[0] = new_cell if new_cell < cell_amount else 0
            return True

        else:
            self.set_proc_sc(code=scs.BIG_RAW_DATA)
            return False


@manager_office()
def run_wss_sim(
    parsing_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    agent = WssSimAgent(
        manager=kwargs["manager"],
        wake_up_parser=parsing_event,
        general_event=general_event,
    )
    agent.run_wss_sim_engine()
