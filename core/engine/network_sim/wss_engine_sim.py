import gc
import time
import traceback
from collections import deque
from multiprocessing.synchronize import Event
from threading import Lock, Thread

import msgspec
from msgspec.json import Encoder

from ... import AgentManager, CorePath, error_handler
from ... import StatusCodes as sc
from ...settings import BacktestingMode as bm


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
    def __init__(self, symbol: str, lock: Lock, mode: int) -> None:
        self.file_path: str = CorePath.data_csv
        self.symbol: str = symbol.upper()
        self.lock = lock
        self.mode = mode
        self.queue: deque = deque(maxlen=10000)
        self.is_running, self.complete = True, False
        self.error: None | str = None

    def start(self) -> None:
        self.subP = Thread(target=self._run, daemon=True)
        self.subP.start()

    def _run(self) -> None:
        try:
            with open(file=self.file_path, mode="r") as f:
                next(f)
                for line in f:
                    if not self.is_running:
                        break

                    while len(self.queue) == self.queue.maxlen:
                        if self.mode == bm.NONE_STOP:
                            time.sleep(0)
                        elif self.mode == bm.ZERO_SLEEP:
                            time.sleep(0)
                        elif self.mode == bm.REAL_TIME_SIM:
                            self.lock.acquire()

                    data: list[str] = line.strip().split(sep=",")
                    obj = AggTradeSim(
                        e="aggTrade",
                        E=int(data[5]),
                        a=int(data[0]),
                        s=self.symbol,
                        p=data[1],
                        q=data[2],
                        f=int(data[3]),
                        l=int(data[4]),
                        T=int(data[5]),
                        m=(data[6] in ("true", "1")),
                    )
                    self.queue.append(obj)

            self.complete = True

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.is_running = False


class WSsSimEngine:
    def __init__(
        self, manager: AgentManager, wake_up_parser: Event, general_event: Event
    ) -> None:
        self.manager = manager
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem

        self.mode = manager.cfgBacktesting.mode
        self.wake_up_parser, self.wait_main = wake_up_parser, general_event
        self.encoder: Encoder = Encoder()
        self.lock = Lock()
        self.prepper: DataPrepper = DataPrepper(
            symbol=self.manager.cfgBacktesting.symbol, lock=self.lock, mode=self.mode
        )

        self.ottrade, self.nttrade = 0, 0  # new|old time trade
        self.min_delta = 0
        # InitGetRawData
        self.cfgRaw = self.manager.cfgRaw
        self.data_size = self.cfgRaw.data_size
        self.header_size = self.cfgRaw.header_size
        self.data_offset: int = self.cfgRaw.data[0]
        self.dataHeader_offset: int = self.cfgRaw.dataHeader[0]
        self.cell_amount = self.cfgRaw.cell_amount
        self.safe_lag = self.cfgRaw.safe_lag
        self.WriterCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.WriterCellCounter)
        ].cast("q")
        self.ReaderCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.ReaderCellCounter)
        ].cast("q")

    @error_handler(set_status_code=True)
    def run_wss_sim_engine(self) -> None:
        # Local Links
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        wake_up_parser, encoder = self.wake_up_parser, self.encoder
        set_status, have_problem = self.set_status, self.have_problem
        have_task = self.have_task
        raw_buf = self.manager.raw_buf
        tts_buf = self.manager.time_to_sleep_buf
        WCellC, RCellC = self.WriterCellCounter, self.ReaderCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount, safe_lag = self.cell_amount, self.safe_lag
        update_cells = self._update_cells
        have_task = self.have_task
        prepper, alarm_clock = self.prepper, self._alarm_clock
        # - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            prepper.start()
            while True:
                stime = time.perf_counter_ns()
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        if wake_up_parser.is_set() is False:
                            wake_up_parser.set()
                        break

                    if prepper.error is None:
                        if not prepper.queue:
                            if prepper.complete:
                                set_status(code=sc.WARN1)

                            if self.lock.locked():
                                self.lock.release()

                            time.sleep(0)
                            continue

                        alarm_clock(
                            tts_buf,
                            stime,
                            WCellC=WCellC,
                            RCellC=RCellC,
                            cell_amount=cell_amount,
                            safe_lag=safe_lag,
                        )
                        set_status(code=WAKE_UP)
                        if update_cells(
                            queue=prepper.queue,
                            encoder=encoder,
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

    def _alarm_clock(
        self,
        tts: memoryview,
        start_time: int,
        WCellC: memoryview,
        RCellC: memoryview,
        cell_amount: int,
        safe_lag: int,
    ) -> None:
        if self.mode == bm.ZERO_SLEEP:
            while ((WCellC[0] - RCellC[0] + cell_amount) % cell_amount) > safe_lag:
                time.sleep(0)

        elif self.mode == bm.NONE_STOP or self.mode == bm.REAL_TIME_SIM:
            if ((WCellC[0] - RCellC[0] + cell_amount) % cell_amount) > safe_lag:
                raise RuntimeError(
                    f"WssAgentSim: AlarmClock: reading lag[\
                ({WCellC[0]} - {RCellC[0]} + {cell_amount}) % {cell_amount}\
                ] > safe lag[{safe_lag}]"
                )

            if self.mode == bm.REAL_TIME_SIM:
                time.sleep(self._time_to_sleep())
                tts[0] = time.perf_counter_ns() - start_time

    def _time_to_sleep(self) -> float:
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

    def _update_cells(
        self,
        queue: deque[AggTradeSim],
        encoder: msgspec.json.Encoder,
        raw_buf: memoryview,
        WCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
    ) -> bool:
        obj: AggTradeSim = queue.popleft()
        self.nttrade: int = obj.T
        raw_data: bytes = encoder.encode(obj)
        if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
            cell: int = WCellC[0]  # get cell
            raw_buf[cell + dataHeader_offset] = lrd  # set lrd on cell[header]
            start: int = cell * data_size + data_offset
            raw_buf[start : start + lrd] = raw_data  # set raw data on cell[data]
            new_cell = cell + 1  # cell for next update
            WCellC[0] = new_cell if new_cell < cell_amount else 0
            return True

        else:
            self.set_status(code=sc.WARN0)
            return False
