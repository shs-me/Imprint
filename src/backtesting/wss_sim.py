import gc
import sys
import time
import traceback
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from src.utils import StatusAgent


class WssSimAgent:
    def __init__(
        self,
        sa: StatusAgent,
        cfg: dict,
        encoder: msgspec.json.Encoder,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
        file_path: str,
    ):
        # Initialization
        self._sa = sa
        self._get, self._set, self._id_m_ = (
            self._sa.get_,
            self._sa.set_,
            self._sa._status(daughter=False),
        )

        self.cfg: dict = cfg
        self.file_path = file_path
        self.encoder = encoder.encode

        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event

        # RawSHM.buf
        self.raw_buf = self._sa.shms["raw"]["buf"]

        # InitSetRawData
        self.ac: int = self.cfg["argg"]["raw"]["ac"]  # Amount Cells
        self.dsib: int = self.cfg["argg"]["raw"]["dsib"]  # Data size in bytes
        self.hsib: int = self.cfg["argg"]["raw"]["hsib"]  # Headers size in bytes
        self.iw: int = self._sa.shms["raw"]["shm"].size - 1  # Index, Write counter

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        sem_sleep_monitoring: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
        file_path: str,
    ):
        try:
            encoder = msgspec.json.Encoder()
            # Init SHM, DebugArray, StatusSHM
            sa = StatusAgent(
                proc_name="network_sim",
                config=cfg["argg"],
                warn_error_status=warn_error_status,
                sem_sleep_monitoring=sem_sleep_monitoring,
            )
            return WssSimAgent(
                sa=sa,
                cfg=cfg,
                encoder=encoder,
                general_event=general_event,
                sem_sleep_parsing=sem_sleep_parsing,
                file_path=file_path,
            )

        except Exception:
            traceback.print_exc()
            warn_error_status.release()
            return None

    def _encode_data(
        self,
        _id_m_,
        encoder,
        _set_status,
        line: str,
    ):  # Line from file convert to raw_data for simulation:
        try:
            data = line.strip().split(",")
            raw_data = encoder(
                {
                    "E": int(data[5]),  # transact_time
                    "p": data[1],  # price
                    "q": data[2],  # quantity
                    "m": bool(data[6]),  # is_buyer_maker
                }
            )
            return raw_data

        except Exception:
            traceback.print_exc()
            _set_status(_id_m_, 153)  # Error in this func
            return False

    def _set_raw_data(
        self,
        iw: int,
        ac: int,
        dsib: int,
        hsib: int,
        _id_m_,
        _set_status,
        raw_buf: memoryview,
        raw_data: bytes,
    ):  # Set Bytes to RawSHM: RING BUFFER
        try:
            lrd = len(raw_data)
            if lrd >= dsib:
                _set_status(_id_m_, 100)  # Warn in this IF
                return False

            iwo = raw_buf[iw]

            if iwo >= (ac * hsib):
                iwn = raw_buf[iw] = hsib
                iwo = 0
            else:
                iwn = raw_buf[iw] = hsib + iwo

            raw_buf[iwo:iwn] = lrd.to_bytes(4, byteorder="little")
            raw_buf[(iwn * ac) : ((iwn * ac) + lrd)] = raw_data

        except Exception:
            traceback.print_exc()
            _set_status(_id_m_, 152)  # Error in this func
            return False

    def run_wss_sim_engine(
        self,
    ):
        # JSON Encoder, SHM.Buf - LocalLink
        _raw_buf, _encoder = self.raw_buf, self.encoder
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = (
            self._id_m_,
            self._set,
            self._get,
        )
        # GetRawData - LocalLink
        _ac, _dsib, _hsib, _iw = self.ac, self.dsib, self.hsib, self.iw
        # Semaphore, Event - LocalLink
        _wait_main, _release_parser = self.wait_main, self.release_parser
        # Methods - LocalLinks
        _set_raw_data, _encode_data = self._set_raw_data, self._encode_data
        # Other - LocalLink
        _file_path = self.file_path
        # - - -
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                try:
                    with open(_file_path, "r") as self.f:
                        next(self.f)
                        for line in self.f:
                            if _get_status(_id_m_) is not True:
                                _set_status(_id_m_, 4)  # IDLE
                                time.sleep(0.005)
                                if _get_status(_id_m_, proc=True):
                                    _set_status(_id_m_, 2)  # Stoping
                                    _release_parser.release()
                                    break

                                _set_status(_id_m_, 5)  # Running # TIME START

                                if (
                                    raw_data := _encode_data(
                                        _id_m_,
                                        _encoder,
                                        _set_status,
                                        line,
                                    )
                                ) is not False:
                                    if (
                                        _set_raw_data(
                                            _iw,
                                            _ac,
                                            _dsib,
                                            _hsib,
                                            _id_m_,
                                            _set_status,
                                            _raw_buf,
                                            raw_data,
                                        )
                                        is not False
                                    ):
                                        _release_parser.release()

                                _set_status(_id_m_, 5)  # END # TIME END

                            else:
                                sys.exit()

                except FileNotFoundError:
                    _set_status(_id_m_, 151)
                    break

            except Exception:
                traceback.print_exc()
                _set_status(_id_m_, 150)
                break


def run_wss_sim(
    config: dict,
    sem_sleep_parsing: Semaphore,
    sem_sleep_monitoring: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):
    gc.disable()

    wss = WssSimAgent.create(
        cfg=config,
        sem_sleep_parsing=sem_sleep_parsing,
        general_event=general_event,
        sem_sleep_monitoring=sem_sleep_monitoring,
        warn_error_status=warn_error_status,
        file_path="data/aggtrades.csv",
    )

    if isinstance(wss, WssSimAgent):
        wss.run_wss_sim_engine()
