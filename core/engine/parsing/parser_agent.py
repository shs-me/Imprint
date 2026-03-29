import gc
import struct
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from ... import Config, MonitorObj
from . import GridEngine


class AggTrade(msgspec.Struct):
    T: int  # Trade time
    p: float  # Price
    q: float  # Quantity
    m: bool  # Is buyer maker?


class ParserAgent:
    def __init__(
        self,
        mo: MonitorObj,
        pre_sleep_wss: Event,
        wake_up_logic: Event,
        general_event: Event,
    ) -> None:
        # Initialization
        __cfg = Config.CoreConfig
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        self.acquire_wss = pre_sleep_wss
        self.wake_up_logic = wake_up_logic
        self.wait_main = general_event
        # variables
        self.decoder = msgspec.json.Decoder(type=AggTrade, strict=False)
        # RawSHM.buf
        self.raw_buf = self._mo.shms[__cfg.Raw.__name__]["buf"]
        self._raw_buf: memoryview = None  # type: ignore
        # MetricsSHM.buf
        self.metrics_buf = self._mo.shms[__cfg.Metrics.__name__]["buf"]
        # InitGetRawData
        self.cell_amount = __cfg.Raw.cell_amount
        self.data_size = __cfg.Raw.data_size
        self.header_size = __cfg.Raw.header_size
        self.flag, self.spare_flag = __cfg.Raw.flag, __cfg.Raw.spare_flag
        self.header_offset = __cfg.Raw.header_offset
        self.data_offset = __cfg.Raw.data_offset
        self.last_cell_offset = __cfg.Raw.last_cell_offset
        self.last_cell = 0

    @staticmethod
    def create(
        pre_sleep_wss: Event,
        wake_up_logic: Event,
        parser_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.parsing.__name__,
                warn_error_status=warn_error_status,
                _monitor=parser_monitor,
            )

            return ParserAgent(
                mo=mo,
                wake_up_logic=wake_up_logic,
                pre_sleep_wss=pre_sleep_wss,
                general_event=general_event,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    def _get_raw_data(
        self,
        flag: int,
        data_size: int,
        dto: tuple[int, int],
        lco: tuple[int, int],
        id_m: int,
        set_status,
        raw_buf: memoryview,
    ) -> memoryview | bool:
        """
        Get RawData[JSON] from RawSHM.\n
        hro: Header Offset
        dto: Data Offset
        lco: Last Cell Offset
        """
        try:
            last_cell = self.last_cell
            if last_cell == 0:
                new_flag: int = 1 if (flag_id := raw_buf[flag]) == 0 else 0
                raw_buf[flag] = new_flag  # change buffer for writer
                _counter: int = 0
                while _counter < 2:
                    if (raw_buf[self.spare_flag] % 2) == 0:  # data is not dirty
                        _raw_buf = (
                            raw_buf[: dto[1]] if flag_id == 0 else raw_buf[dto[1] :]
                        )
                        cell_id: int = struct.unpack("!q", _raw_buf[lco[0] : lco[1]])[0]
                        last_cell, self._raw_buf = cell_id, _raw_buf

                    else:  # data maybe is dirty
                        _counter += 1

            lrd = self.raw_buf[last_cell]
            cell_id = last_cell - 1
            start = cell_id * data_size + dto[0]
            end = start + lrd
            raw_data = self._raw_buf[start:end]
            self.last_cell = cell_id
            return raw_data

        except Exception:
            traceback.print_exc()
            set_status(id_m, 154)
            return False

    def _decode_raw_data(
        self, raw_data: memoryview, decoder, id_m_: int, set_status
    ) -> AggTrade | bool | None:
        """Decode RawData[JSON] to Struct AggTrade"""
        try:
            trade = decoder(raw_data)
            if trade.p < 0 or trade.q < 0 or trade.T < 0:
                return None

            return trade

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m_, 153)
            return False

    def run_parsing_engine(self) -> None:
        # LocalLinks
        _raw_buf, _metrics_buf = self.raw_buf, self.metrics_buf  # ShM.Buf's
        _decoder = self.decoder.decode  # Msgspec Json Decoder
        # MonitorObj
        _id_m, set_status, get_status = self._id_m_, self._set, self._get
        # GetRawData
        flag, header_size, data_size = self.flag, self.header_size, self.data_size
        cell_amount, dto, hro = self.cell_amount, self.data_offset, self.header_offset
        lco = self.last_cell_offset
        # Semaphore, Event
        wake_up_logic, pre_sleep_wss = self.wake_up_logic, self.acquire_wss
        # Methods
        get_raw_data = self._get_raw_data
        decode_raw_data = self._decode_raw_data
        #  - - -
        try:
            engine = GridEngine.create(_mo_=self._mo)
            if isinstance(engine, GridEngine):
                while True:
                    try:
                        gc.collect()
                        self.wait_main.wait()
                        while True:
                            if get_status(_id_m) is not True:
                                set_status(_id_m, 4)  # IDLE # TIME START
                                if self.last_cell == 0:
                                    pre_sleep_wss.wait()

                                if get_status(_id_m, proc=True):
                                    wake_up_logic.wait()
                                    break

                                set_status(_id_m, 5)  # Running # TIME WAKE_UP
                                if isinstance(
                                    (
                                        raw_data := get_raw_data(
                                            flag=flag,
                                            data_size=data_size,
                                            dto=dto,
                                            lco=lco,
                                            id_m=_id_m,
                                            set_status=set_status,
                                            raw_buf=_raw_buf,
                                        )
                                    ),
                                    memoryview,
                                ):
                                    if isinstance(
                                        (
                                            trade := decode_raw_data(
                                                raw_data=raw_data,
                                                decoder=_decoder,
                                                id_m_=_id_m,
                                                set_status=set_status,
                                            )
                                        ),
                                        AggTrade,
                                    ):
                                        if engine.update(
                                            price=trade.p,
                                            qty=trade.q,
                                            timestamp=trade.T,
                                            is_sell=trade.m,
                                        ):
                                            if wake_up_logic.is_set() is False:
                                                wake_up_logic.set()

                                    elif trade is False:
                                        sys.exit()

                                elif raw_data is False:
                                    sys.exit()

                            else:
                                sys.exit()

                    except Exception:
                        traceback.print_exc()  # Debug
                        set_status(_id_m, 150)  # Error in this func
                        break
            else:
                set_status(_id_m, 151)  # Error in engine
                return

        except Exception:
            traceback.print_exc()  # Debug
            set_status(_id_m, 150)  # Error in this func


def run_parsing(
    pre_sleep_wss: Event,
    wake_up_logic: Event,
    parser_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    agent = ParserAgent.create(
        pre_sleep_wss=pre_sleep_wss,
        wake_up_logic=wake_up_logic,
        parser_monitor=parser_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, ParserAgent):
        agent.run_parsing_engine()
