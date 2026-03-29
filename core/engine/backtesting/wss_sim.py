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
        wake_up_parser: Event,
        general_event: Event,
    ) -> None:
        # Initialization
        __cfg = Config.CoreConfig
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        # Encoder, Variables
        self.encoder: msgspec.json.Encoder = msgspec.json.Encoder()
        self.ottrade: int = 0  # old time trade
        self.nttrade: int = 0  # new time trade
        # Semaphore, Event
        self.release_parser = wake_up_parser
        self.wait_main = general_event
        # RawSHM.buf
        self.raw_buf = self._mo.shms[__cfg.Raw.__name__]["buf"]
        # InitGetRawData
        self.cell_amount = __cfg.Raw.cell_amount
        self.data_size = __cfg.Raw.data_size
        self.header_size = __cfg.Raw.header_size
        self.flag, self.spare_flag = __cfg.Raw.flag, __cfg.Raw.spare_flag
        self.header_offset = __cfg.Raw.header_offset
        self.data_offset = __cfg.Raw.data_offset
        self.last_cell_offset = __cfg.Raw.last_cell_offset

    @staticmethod
    def create(
        wake_up_parser: Event,
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
                mo=mo, general_event=general_event, wake_up_parser=wake_up_parser
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
        dto: tuple[int, int],
        lco: tuple[int, int],
        id_m: int,
        set_status,
        raw_buf: memoryview,
    ) -> bool:
        """
        Set RawData[JSON Bytes] to RawSHM.\n
        hro: Header Offset
        dto: Data Offset
        lco: Last Cell Offset
        """
        try:
            lrd: int = len(raw_data)  # lrd: Len Raw Data
            if lrd < data_size:
                flag_id: int = self.raw_buf[flag]
                _raw_buf = raw_buf[: dto[1]] if flag_id == 0 else raw_buf[dto[1] :]
                _raw_buf[self.spare_flag] = 1  # data maybe is dirty

                cell_id: int = struct.unpack("!q", _raw_buf[lco[0] : lco[1]])[0]

                if cell_id >= (cell_amount * header_size):
                    cell_id_new = header_size
                    cell_id = 0
                else:
                    cell_id_new = cell_id + header_size

                _raw_buf[lco[0] : lco[1]] = struct.pack("!q", cell_id_new)
                _raw_buf[cell_id_new + lco[1]] = lrd
                start = cell_id * data_size + dto[0]
                end = start + lrd
                _raw_buf[start:end] = raw_data

                _raw_buf[self.spare_flag] = 0  # data is not dirty
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
        wake_up_parser = self.release_parser  # Semaphore
        _raw_buf = self.raw_buf  # RawShM.buf
        _encoder = self.encoder  # JSON msgspec Encoder
        id_m, set_status, get_status = self._id_m_, self._set, self._get
        flag, header_size, data_size = self.flag, self.header_size, self.data_size
        cell_amount, dto, hro = self.cell_amount, self.data_offset, self.header_offset
        lco = self.last_cell_offset
        set_raw_data, encode_data = self._set_raw_data, self._encode_data
        time_to_sleep = self._time_to_sleep
        # - - -
        while True:
            try:
                gc.collect()
                self.wait_main.wait()
                set_status(id_m, 4)  # IDLE
                prepper = DataPrepper()
                prepper.start()
                while True:
                    if get_status(id_m) is not True:
                        set_status(id_m, 4)  # Sleep
                        if get_status(id_m, proc=True):
                            if wake_up_parser.is_set() is False:
                                wake_up_parser.set()
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
                                    flag=flag,
                                    cell_amount=cell_amount,
                                    header_size=header_size,
                                    data_size=data_size,
                                    dto=dto,
                                    lco=lco,
                                    id_m=id_m,
                                    set_status=set_status,
                                    raw_buf=_raw_buf,
                                ):
                                    if wake_up_parser.is_set() is False:
                                        wake_up_parser.set()

                                else:
                                    if _state is False:
                                        return
                            else:
                                if raw_data is False:
                                    return
                        else:
                            set_status(id_m, 151)
                            print(prepper.error)  # Debug
                            continue
                    else:
                        return

            except Exception:
                traceback.print_exc()  # Debug
                set_status(id_m, 150)
                break


def run_wss_sim(
    wake_up_parser: Event,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()

    wss = WssSimAgent.create(
        wake_up_parser=wake_up_parser,
        general_event=general_event,
        network_monitor=network_monitor,
        warn_error_status=warn_error_status,
    )

    if isinstance(wss, WssSimAgent):
        wss.run_wss_sim_engine()
