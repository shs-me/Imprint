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
    ):
        # Initialization
        self._mo = mo
        self._get, self._set, self._id_m_ = (
            self._mo.get_,
            self._mo.set_,
            self._mo._status(daughter=False),
        )

        self.cfg: dict = cfg
        self.file_path = self.cfg["argg"]["data_path"]
        self.encoder = encoder.encode

        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event

        # RawSHM.buf
        self.raw_buf = self._mo.shms["raw"]["buf"]

        # InitSetRawData
        self.header_memory: list[int] = self.cfg["argg"]["raw"]["header_memory"]
        self.data_size: int = self.cfg["argg"]["raw"]["data_size"]
        self.flag_r: int = self.cfg["argg"]["raw"]["flag_r"]
        self.flag_w: int = self.cfg["argg"]["raw"]["flag_w"]

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
            traceback.print_exc()
            warn_error_status.release()
            return None

    # Encode ListStr to Bytes Json structure
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
            return raw_data

        except Exception:
            traceback.print_exc()
            _set_status(_id_m_, 153)  # Error in this func
            return False

    # Set Bytes to RawSHM
    def _set_raw_data(
        self,
        flag_w: int,
        flag_r: int,
        data_size: int,
        header_memory: list[int],
        _id_m_,
        _set_status,
        raw_buf: memoryview,
        raw_data: bytes,
    ) -> bool | None:
        try:
            lrd = len(raw_data)
            if lrd < data_size:
                if raw_buf[flag_r] == 4:  # Idle r
                    raw_buf[flag_w] = 5  # Working w...
                    raw_buf[header_memory[0] : header_memory[1]] = lrd.to_bytes(8)
                    raw_buf[:lrd] = raw_data
                    raw_buf[flag_w] = 4  # Idle w
                    return True

                elif raw_buf[flag_r] == 5:  # Working r...
                    # - - -
                    return None

            else:
                _set_status(_id_m_, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()
            _set_status(_id_m_, 152)  # Error in this func
            return False

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
        # GetRawData - LocalLink
        flag_w, flag_r, data_size, header_memory = (
            self.flag_w,
            self.flag_r,
            self.data_size,
            self.header_memory,
        )
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
                _set_status(_id_m_, 4)  # IDLE
                _release_parser.acquire(timeout=3)
                try:
                    with open(_file_path, "r") as self.f:
                        next(self.f)
                        for line in self.f:
                            if _get_status(_id_m_) is not True:
                                _set_status(_id_m_, 4)  # Sleep
                                time.sleep(0.01)
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
                                            flag_w,
                                            flag_r,
                                            data_size,
                                            header_memory,
                                            _id_m_,
                                            _set_status,
                                            _raw_buf,
                                            raw_data,
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
                traceback.print_exc()
                _set_status(_id_m_, 150)
                break


def run_wss_sim(
    config: dict,
    sem_sleep_parsing: Semaphore,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):
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
