import gc
import struct
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
        self,
        mo: MonitorObj,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
    ) -> None:
        # Initialization
        cfg = Config.CoreConfig
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        # Encoder, Variables
        self.encoder: msgspec.json.Encoder = msgspec.json.Encoder()
        self.ottrade: int = 0  # old time trade
        self.nttrade: int = 0  # new time trade
        # Semaphore, Event
        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event
        # RawSHM.buf
        self.raw_buf = self._mo.shms[cfg.Raw.__name__]["buf"]
        # InitGetRawData
        self.cell_amount = cfg.Raw.cell_amount
        self.data_size = cfg.Raw.data_size
        self.header_size = cfg.Raw.header_size
        self.flag = cfg.Raw.flag
        self.cell_start_offset = cfg.Raw.cell_start_offset
        self.cell_end_slice = slice(*cfg.Raw.cell_end_offset)

    @staticmethod
    def create(
        sem_sleep_parsing: Semaphore,
        network_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.network_sim.__name__,
                warn_error_status=warn_error_status,
                _monitor=network_monitor,
            )
            return WssSimAgent(
                mo=mo, general_event=general_event, sem_sleep_parsing=sem_sleep_parsing
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    def _encode_data(
        self, prepper: DataPrepper, encoder: msgspec.json.Encoder, id_m: int, set_status
    ) -> bytes | bool:
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
            set_status(id_m, 153)  # Error in this func
            return False

    def _set_raw_data(
        self,
        raw_data: bytes,
        flag: int,
        cell_amount: int,
        header_size: int,
        data_size: int,
        id_m: int,
        set_status,
        raw_buf: memoryview,
    ) -> bool:
        """Set RawData[JSON Bytes] to RawSHM"""
        try:
            lrd: int = len(raw_data)  # lrd: Len Raw Data
            if lrd < data_size:
                _counter: int = 0
                while _counter < 2:
                    flag_id: int = raw_buf[flag]
                    # . . .
                    cell_id: int = struct.unpack("!q", raw_buf[self.cell_end_slice])[0]
                    if (cell_id + 1) >= (cell_amount * header_size):
                        cell_id_new = self.cell_start_offset + header_size
                        cell_id = self.cell_start_offset
                    else:
                        cell_id_new = cell_id + header_size

                    raw_buf[self.cell_end_slice] = struct.pack("!q", cell_id)
                    raw_buf[cell_id] = lrd  # Set lrd To Next Cell Hsib
                    # Set RawData To Next Cell Dsib
                    raw_buf[
                        (cell_id_new * cell_amount) : ((iwn * cell_amount) + lrd)
                    ] = raw_data
                    return True

            else:
                set_status(id_m, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 152)  # Error in this func
            return False

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

    def run_wss_sim_engine(self) -> None:
        # Local Links
        _release_parser = self.release_parser  # Semaphore
        _raw_buf = self.raw_buf  # RawShM.buf
        _encoder = self.encoder  # JSON msgspec Encoder
        id_m, set_status, get_status = self._id_m_, self._set, self._get
        _cell_amount, _header_size = self.cell_amount, self.header_size
        _data_size, _flag, _flag_start = self.data_size, self.flag, self.flag_start
        set_raw_data, encode_data = self._set_raw_data, self._encode_data
        time_to_sleep = self._time_to_sleep
        # - - -
        while True:
            try:
                gc.collect()
                self.wait_main.wait()
                set_status(id_m, 4)  # IDLE
                prepper = DataPrepper()
                while _raw_buf[_flag_start] != 1:
                    time.sleep(0.1)

                prepper.start()
                while True:
                    if get_status(id_m) is not True:
                        set_status(id_m, 4)  # Sleep
                        if get_status(id_m, proc=True):
                            _release_parser.release()
                            break

                        if prepper.error is None:
                            if not prepper.queue:
                                time.sleep(0.0001)
                                continue

                            time.sleep(time_to_sleep())
                            set_status(id_m, 5)  # WakeUp
                            if isinstance(
                                (
                                    raw_data := encode_data(
                                        prepper=prepper,
                                        encoder=_encoder,
                                        id_m=id_m,
                                        set_status=set_status,
                                    )
                                ),
                                bytes,
                            ):
                                if _state := set_raw_data(
                                    raw_data=raw_data,
                                    flag=_flag,
                                    cell_amount=_cell_amount,
                                    header_size=_header_size,
                                    data_size=_data_size,
                                    id_m=id_m,
                                    set_status=set_status,
                                    raw_buf=_raw_buf,
                                ):
                                    _release_parser.release()

                                else:
                                    if _state is False:
                                        pass
                            else:
                                if raw_data is False:
                                    pass
                        else:
                            set_status(id_m, 151)
                            print(prepper.error)  # Debug
                            continue
                    else:
                        break

            except Exception:
                traceback.print_exc()  # Debug
                set_status(id_m, 150)
                break


def run_wss_sim(
    sem_sleep_parsing: Semaphore,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()

    wss = WssSimAgent.create(
        sem_sleep_parsing=sem_sleep_parsing,
        general_event=general_event,
        network_monitor=network_monitor,
        warn_error_status=warn_error_status,
    )

    if isinstance(wss, WssSimAgent):
        wss.run_wss_sim_engine()
