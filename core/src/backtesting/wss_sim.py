import gc
import time
import traceback
from collections import deque
from multiprocessing.synchronize import Event, Semaphore
from threading import Thread

import msgspec

from .. import MonitorObj


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
        config: dict,
    ) -> None:
        # Initialization
        self.cfg: dict = config
        self.file_path = self.cfg["argg"]["data_path"]
        self.symbol: str = str(self.cfg["argg"]["symbol"]).upper()
        self.queue = deque(maxlen=10000)
        self.is_running = True
        self.error = None

    def start(
        self,
    ) -> None:
        "Run Daemon Thread"
        Thread(target=self._run, daemon=True).start()

    def _run(
        self,
    ) -> None:
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
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._get, self._set, self._id_m_ = (
            self._mo.get_,
            self._mo.set_,
            self._mo._status(daughter=False),
        )

        self.cfg: dict = cfg
        # Encoder, Variables
        self.encoder: msgspec.json.Encoder = msgspec.json.Encoder()
        self.ottrade: int = 0  # old time trade
        self.nttrade: int = 0  # new time trade
        # Semaphore, Event
        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event
        # RawSHM.buf
        self.raw_buf = self._mo.shms["raw"]["buf"]
        # InitSetRawData
        self.ac = self.cfg["argg"]["raw"]["ac"]  # Amount Cells
        self.dsib = self.cfg["argg"]["raw"]["dsib"]  # Data size in bytes
        self.hsib = self.cfg["argg"]["raw"]["hsib"]  # Headers size in bytes
        self._iw = self._mo.shms["raw"]["shm"].size - 1  # Index, Write counter
        self._sssd = self._mo.shms["raw"]["shm"].size - 3  # Index, Start Start Set Data

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        network_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            # Init SHM, profilingArray, StatusSHM
            mo = MonitorObj(
                proc_name="network_sim",
                config=cfg["argg"],
                warn_error_status=warn_error_status,
                _monitor=network_monitor,
            )
            return WssSimAgent(
                mo=mo,
                cfg=cfg,
                general_event=general_event,
                sem_sleep_parsing=sem_sleep_parsing,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    # Encode AggTradeSim Obj to Bytes Json structure
    # Also set, new time trade
    def _encode_data(
        self,
        _id_m_: int,
        encoder: msgspec.json.Encoder,
        _set_status,
        prepper,
    ) -> bytes | bool:
        try:
            obj = prepper.queue.popleft()
            raw_data = encoder.encode(obj)
            self.nttrade = obj.E
            return raw_data

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 153)  # Error in this func
            return False

    # Set Bytes to RawSHM
    def _set_raw_data(
        self,
        ac: int,
        iw: int,
        hsib: int,
        dsib: int,
        _id_m_,
        _set_status,
        raw_buf: memoryview,
        raw_data: bytes,
    ) -> bool:
        try:
            lrd = len(raw_data)  # lrd: Len Raw Data
            if lrd < dsib:  # dsib: Data Size in Bytes
                iwo = raw_buf[iw]  # iwo: Index Write Old
                if (iwo + 1) >= (ac * hsib):  # ac: Amount Cells
                    # hsib: Headers Size In Bytes
                    iwn = raw_buf[iw] = hsib  # iwn: Index Write New
                    iwo = 0
                else:
                    iwn = raw_buf[iw] = hsib + iwo

                # Set lrd To Next Cell Hsib
                raw_buf[iwo] = lrd
                # Set RawData To Next Cell Dsib
                raw_buf[(iwn * ac) : ((iwn * ac) + lrd)] = raw_data
                return True
            else:
                _set_status(_id_m_, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 152)  # Error in this func
            return False

    # Return Base OR Sim Time To Sleep
    def _time_to_sleep(
        self,
    ) -> float:
        # ott: Old Time Trade | ntt: New Time Trade
        ott, ntt = self.ottrade, self.nttrade
        # - - -
        if 0 < ott:
            if ott <= ntt:
                if ott < ntt:
                    self.ottrade = ntt

                return (ntt - ott) / 1000  # tts: Time To Sleep

        else:
            self.ottrade = ntt

        return 0.01  # btts: Base Time To Sleep

    def run_wss_sim_engine(
        self,
    ) -> None:
        # Local Links
        _release_parser = self.release_parser  # Semaphore
        _raw_buf = self.raw_buf  # RawShM.buf
        _encoder = self.encoder  # JSON msgspec Encoder
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get
        ac, iw, hsib, dsib, sssd = self.ac, self._iw, self.hsib, self.dsib, self._sssd
        _set_raw_data, _encode_data, _time_to_sleep = (
            self._set_raw_data,
            self._encode_data,
            self._time_to_sleep,
        )
        # - - -
        while True:
            try:
                gc.collect()
                self.wait_main.wait()
                _set_status(_id_m_, 4)  # IDLE
                prepper = DataPrepper(config=self.cfg)
                while _raw_buf[sssd] != 1:
                    time.sleep(0.1)

                prepper.start()
                while True:
                    if _get_status(_id_m_) is not True:
                        _set_status(_id_m_, 4)  # Sleep
                        if _get_status(_id_m_, proc=True):
                            _release_parser.release()
                            break

                        if prepper.error is None:
                            if not prepper.queue:
                                time.sleep(0.0001)
                                continue

                            time.sleep(_time_to_sleep())
                            _set_status(_id_m_, 5)  # WakeUp
                            if isinstance(
                                (
                                    raw_data := _encode_data(
                                        _id_m_,
                                        _encoder,
                                        _set_status,
                                        prepper,
                                    )
                                ),
                                bytes,
                            ):
                                if _state := _set_raw_data(
                                    ac=ac,
                                    iw=iw,
                                    hsib=hsib,
                                    dsib=dsib,
                                    _id_m_=_id_m_,
                                    _set_status=_set_status,
                                    raw_buf=_raw_buf,
                                    raw_data=raw_data,
                                ):
                                    _release_parser.release()

                                else:
                                    if _state is False:
                                        pass
                            else:
                                if raw_data is False:
                                    pass
                        else:
                            _set_status(self._id_m_, 151)
                            print(prepper.error)  # Debug
                            continue
                    else:
                        break

            except Exception:
                traceback.print_exc()  # Debug
                _set_status(_id_m_, 150)
                break


def run_wss_sim(
    config: dict,
    sem_sleep_parsing: Semaphore,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()

    wss = WssSimAgent.create(
        cfg=config,
        sem_sleep_parsing=sem_sleep_parsing,
        general_event=general_event,
        network_monitor=network_monitor,
        warn_error_status=warn_error_status,
    )

    if isinstance(wss, WssSimAgent):
        wss.run_wss_sim_engine()
