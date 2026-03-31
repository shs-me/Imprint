import gc
import time
import traceback
from collections import deque
from multiprocessing.synchronize import Event, Semaphore
from threading import Thread

import msgspec

from ... import Config, MonitorObj


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
        # Initialization
        self.file_path = Config.CorePath.data_csv
        self.symbol: str = Config.UserConfig.symbol.upper()
        self.queue = deque(maxlen=10000)
        self.is_running = True
        self.error = None

    def start(self) -> None:
        "Run Daemon Thread"
        Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            with open(self.file_path, "r") as f:
                next(f)
                for line in f:
                    if not self.is_running:
                        break

                    d = line.strip().split(",")
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


class WssSimAgent:
    def __init__(
        self, mo: MonitorObj, wake_up_parser: Event, general_event: Event
    ) -> None:
        __cfg, self._mo = Config.CoreConfig, mo
        self.id_m = self._mo.id_m
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.encoder: msgspec.json.Encoder = msgspec.json.Encoder()
        self.ottrade, self.nttrade = 0, 0  # new|old time trade
        self.wake_up_parser, self.wait_main = wake_up_parser, general_event
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset = __cfg.Raw.data_offset[0]
        self.header_offset = __cfg.Raw.header_offset[0]
        self.cell_amount, self.safe_lag = __cfg.Raw.cell_amount, __cfg.Raw.safe_lag
        # SHM.buf
        self.raw_buf = self._mo.shms[__cfg.Raw.__name__]["buf"]
        self.ncell_wr = self.raw_buf[
            __cfg.Raw.ncell_offset[0] : __cfg.Raw.ncell_offset[1]
        ].cast("q")

    def _time_to_sleep(self) -> float:
        """Return BaseTimeToSleep OR SimTimeToSleep"""
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

    def _encode_data(
        self, prepper: DataPrepper, encoder: msgspec.json.Encoder
    ) -> bytes | None:
        """
        Encode AggTradeSim Obj to Json Bytes.\n
        Also set, new time trade.
        """
        try:
            obj = prepper.queue.popleft()
            raw_data = encoder.encode(obj)
            self.nttrade = obj.E
            return raw_data

        except Exception:
            traceback.print_exc()  # Debug
            self.set_status(id_m=self.id_m, code=153)  # Error in this func
            return None

    def _set_raw_data(
        self,
        raw_data: bytes,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_size: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
        safe_lag: float,
    ) -> bool:
        """
        Set RawData[JSON Bytes] to RawSHM.\n
        ncell_wr: number cell writer & reader
        """
        try:
            if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
                ncell_w, ncell_r = ncell_wr[0], ncell_wr[1]
                if ((ncell_w - ncell_r + cell_amount) % cell_amount) > safe_lag:
                    self.set_status(id_m=self.id_m, code=101)  # Warn in this IF
                    return False

                raw_buf[ncell_w + header_offset] = lrd
                start = ncell_w * data_size + data_offset
                raw_buf[start : start + lrd] = raw_data
                ncell_wr[0] = (
                    ncell_w if (ncell_w := ncell_w + header_size) < cell_amount else 0
                )
                return True

            else:
                self.set_status(id_m=self.id_m, code=100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            self.set_status(id_m=self.id_m, code=152)  # Error in this func
            return False

    def run_wss_sim_engine(self) -> None:
        # Local Links
        wake_up_parser, encoder = self.wake_up_parser, self.encoder
        id_m, set_status, have_problem = self.id_m, self.set_status, self.have_problem
        header_size, data_size = self.header_size, self.data_size
        data_offset, header_offset = self.data_offset, self.header_offset
        raw_buf, ncell_wr, cell_amount = self.raw_buf, self.ncell_wr, self.cell_amount
        safe_lag = self.safe_lag
        set_raw_data, encode_data = self._set_raw_data, self._encode_data
        time_to_sleep = self._time_to_sleep
        # - - -
        try:
            while True:
                gc.collect()
                self.wait_main.wait()
                set_status(id_m, 4)  # IDLE
                prepper = DataPrepper()
                prepper.start()
                while True:
                    if have_problem(id_m=id_m, daugther=True) is not True:
                        set_status(id_m, 4)  # Sleep
                        if have_problem(id_m, proc=True):
                            if wake_up_parser.is_set() is False:
                                wake_up_parser.set()

                            break

                        if prepper.error is None:
                            if not prepper.queue:
                                time.sleep(0.0001)
                                continue

                            time.sleep(time_to_sleep())
                            set_status(id_m, 5)  # WakeUp
                            if raw_data := encode_data(
                                prepper=prepper, encoder=encoder
                            ):
                                if set_raw_data(
                                    raw_data=raw_data,
                                    raw_buf=raw_buf,
                                    ncell_wr=ncell_wr,
                                    cell_amount=cell_amount,
                                    header_size=header_size,
                                    header_offset=header_offset,
                                    data_size=data_size,
                                    data_offset=data_offset,
                                    safe_lag=safe_lag,
                                ):
                                    if wake_up_parser.is_set() is False:
                                        wake_up_parser.set()

                        else:
                            set_status(id_m, 151)
                            print(prepper.error)  # Debug
                            continue
                    else:
                        return

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 150)


def run_wss_sim(
    wake_up_parser: Event,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    try:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.network_sim.__name__,
                warn_error_status=warn_error_status,
                _monitor=network_monitor,
            )
        except Exception:
            return

        agent = WssSimAgent(
            mo=mo, general_event=general_event, wake_up_parser=wake_up_parser
        )
        agent.run_wss_sim_engine()
        agent = None

    finally:
        gc.collect()
