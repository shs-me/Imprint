import gc
import sys
import time
import traceback
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from .. import MonitorObj


class WssSimAgent:
    def __init__(
        self,
        mo: MonitorObj,
        cfg: dict,
        encoder: msgspec.json.Encoder,
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
        self.file_path = self.cfg["argg"]["data_path"]
        # Encoder, Variables
        self.encoder = encoder.encode
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
            encoder = msgspec.json.Encoder()
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
                encoder=encoder,
                general_event=general_event,
                sem_sleep_parsing=sem_sleep_parsing,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    # Encode ListStr to Bytes Json structure
    # Also set, new time trade
    def _encode_data(
        self,
        _id_m_,
        encoder,
        _set_status,
        line: str,
    ) -> bytes | bool:
        try:
            data = line.strip().split(",")
            raw_data: bytes = encoder(
                {
                    "E": int(data[5]),  # transact_time
                    "p": data[1],  # price
                    "q": data[2],  # quantity
                    "m": bool(data[6]),  # is_buyer_maker
                }
            )
            self.nttrade = int(data[5])
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
        # JSON Encoder, SHM.Buf - LocalLink
        _raw_buf, _encoder = self.raw_buf, self.encoder
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = (
            self._id_m_,
            self._set,
            self._get,
        )
        # SetRawData - LocalLink
        ac, iw, hsib, dsib, sssd = self.ac, self._iw, self.hsib, self.dsib, self._sssd
        # Semaphore, Event - LocalLink
        _wait_main, _release_parser = self.wait_main, self.release_parser
        # Methods - LocalLinks
        _set_raw_data, _encode_data, _time_to_sleep = (
            self._set_raw_data,
            self._encode_data,
            self._time_to_sleep,
        )
        # Other - LocalLink
        _file_path = self.file_path
        # - - -
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                _set_status(_id_m_, 4)  # IDLE
                while _raw_buf[sssd] != 1:
                    time.sleep(0.1)
                try:
                    with open(_file_path, "r") as f:
                        next(f)
                        for line in f:
                            if _get_status(_id_m_) is not True:
                                _set_status(_id_m_, 4)  # Sleep
                                time.sleep(_time_to_sleep())
                                if _get_status(_id_m_, proc=True):
                                    _release_parser.release()
                                    break

                                _set_status(_id_m_, 5)  # WakeUp
                                if isinstance(
                                    (
                                        raw_data := _encode_data(
                                            _id_m_,
                                            _encoder,
                                            _set_status,
                                            line,
                                        )
                                    ),
                                    bytes,
                                ):
                                    if (
                                        _state := _set_raw_data(
                                            ac=ac,
                                            iw=iw,
                                            hsib=hsib,
                                            dsib=dsib,
                                            _id_m_=_id_m_,
                                            _set_status=_set_status,
                                            raw_buf=_raw_buf,
                                            raw_data=raw_data,
                                        )
                                        is True
                                    ):
                                        _release_parser.release()

                                    else:
                                        if _state is False:
                                            pass
                                else:
                                    if raw_data is False:
                                        pass
                            else:
                                sys.exit()

                except FileNotFoundError:
                    _set_status(_id_m_, 151)
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
