import gc
import time
import traceback
from collections import deque
from multiprocessing.synchronize import Event
from threading import Thread

import msgspec
from msgspec.json import Encoder

from ... import Config, ManagerAgent
from ... import StatusCodes as sc
from .. import error_action


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
    def __init__(self) -> None:
        self.file_path: str = Config.CorePath.data_csv
        self.symbol: str = Config.UserConfig.symbol.upper()
        self.queue: deque = deque(maxlen=10000)
        self.is_running = True
        self.error: None | str = None

    def start(self) -> None:
        Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            with open(file=self.file_path, mode="r") as f:
                next(f)
                for line in f:
                    if not self.is_running:
                        break

                    d: list[str] = line.strip().split(sep=",")
                    obj = AggTradeSim(
                        e="aggTrade",
                        E=int(d[5]),
                        a=int(d[0]),
                        s=self.symbol,
                        p=d[1],
                        q=d[2],
                        f=int(d[3]),
                        l=int(d[4]),
                        T=int(d[5]),
                        m=(d[6] in ("true", "1")),
                    )
                    self.queue.append(obj)
                    while len(self.queue) == self.queue.maxlen:
                        time.sleep(0.001)

        except Exception as e:
            self.error = f"Prepper Error: {e}\n{traceback.format_exc()}"
            self.is_running = False


class WSsSimEngine:
    def __init__(
        self, manager: ManagerAgent, wake_up_parser: Event, general_event: Event
    ) -> None:
        __cfg, self.manager = Config.ShmSharing, manager
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.wake_up_parser, self.wait_main = wake_up_parser, general_event
        self.encoder: Encoder = Encoder()
        self.prepper: DataPrepper = DataPrepper()
        self.ottrade, self.nttrade = 0, 0  # new|old time trade
        self.count_delta, self.sum_delta, self.ma = 0, 0, 1
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset: int = __cfg.Raw.data_offset[0]
        self.header_offset: int = __cfg.Raw.header_offset[0]
        self.cell_amount = __cfg.Raw.cell_amount
        self.ncell_wr: memoryview[int] = self.manager.raw_buf[
            slice(*__cfg.Raw.ncell_offset)
        ].cast("q")

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

        return 0.01  # Base Time To Sleep

    def _alarm_clock(self, start_time: int, end_time: int) -> None:
        self.sum_delta += end_time - start_time
        self.count_delta += 1
        self.ma = self.sum_delta // self.count_delta

    def _encode_data(
        self, prepper: DataPrepper, encoder: msgspec.json.Encoder
    ) -> bytes | None:
        obj: AggTradeSim = prepper.queue.popleft()
        raw_data: bytes = encoder.encode(obj)
        self.nttrade: int = obj.E
        return raw_data

    def _set_raw_data(
        self,
        raw_data: bytes,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
    ) -> bool:
        if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
            ncell_w: int = ncell_wr[0]  # get cell
            raw_buf[ncell_w + header_offset] = lrd  # set lrd on cell[header]
            start: int = ncell_w * data_size + data_offset
            raw_buf[start : start + lrd] = raw_data  # set raw data on cell[data]
            ncell_w_new = ncell_w + 1  # cell for next update
            ncell_wr[0] = ncell_w_new if ncell_w_new < cell_amount else 0
            return True

        else:
            self.set_status(code=sc.WARN0)
            return False

    @error_action(set_sc=True)
    def run_wss_sim_engine(self) -> None:
        # Local Links
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        wake_up_parser, encoder = self.wake_up_parser, self.encoder
        set_status, have_problem = self.set_status, self.have_problem
        data_size = self.data_size
        data_offset, header_offset = self.data_offset, self.header_offset
        raw_buf, ncells, acell = self.manager.raw_buf, self.ncell_wr, self.cell_amount
        set_raw_data, encode_data = self._set_raw_data, self._encode_data
        time_to_sleep, have_task = self._time_to_sleep, self.have_task
        prepper = self.prepper
        # - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            prepper.start()
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        if wake_up_parser.is_set() is False:
                            wake_up_parser.set()
                        break

                    if prepper.error is None:
                        if not prepper.queue:
                            time.sleep(0)
                            continue

                        time.sleep(time_to_sleep())
                        set_status(code=WAKE_UP)
                        if raw_data := encode_data(prepper=prepper, encoder=encoder):
                            if set_raw_data(
                                raw_data=raw_data,
                                raw_buf=raw_buf,
                                ncell_wr=ncells,
                                cell_amount=acell,
                                header_offset=header_offset,
                                data_size=data_size,
                                data_offset=data_offset,
                            ):
                                if wake_up_parser.is_set() is False:
                                    wake_up_parser.set()
                    else:
                        raise RuntimeError(prepper.error)
                else:
                    return
