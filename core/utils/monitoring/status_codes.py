from __future__ import annotations

from enum import IntEnum


class StatusCodes(IntEnum):
    label: str

    def __new__(cls, sc_label: str):
        if len(cls.__members__) >= 64:
            raise ValueError("StatusCodes >= 64, but type: int64")

        value = 1 << len(cls.__members__)
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.label = sc_label
        return obj

    # General PROC/TASK SC
    RUN = "RUNNING"
    STOP = "STOPING"
    EXIT = "EXIT"
    SLEEP = "SLEEPING"
    WAKE_UP = "WAKE_UP"
    COMPLETE = "COMPLETE AND EXIT"
    ERROR = "ERROR[MORE INFO IN 'EXC_DUMP']"
    GC_COLLECT = "Collect garbage"
    # - - -
    # PARSING
    # PROC_SC
    UNVALID_DATA = "PARSING: _update_cells[ aggTradeData[price,qty or timestamp] < 0 ]"
    FP_INIT_FAILED = "PARSING: FootprintWriter: init_session: amount tick in nPrice > 80% array[fpLines]"
    FP_IDX_FILLED = "PARSING: FootprintWriter: update: array[fpCols] < idx or idx < 0"
    FP_IDY_FILLED = "PARSING: FootprintWriter: update: array[fpLines] < idy or idy < 0"
    # TASK_SC
    FP_RE_INIT = ""
    # - - -
    # NETWORK/SIM
    BIG_RAW_DATA = "NETWORK/SIM: wss: _set_raw_data: size/len raw_data > data_cell_size_in_ring_buffer"
    DATA_PREPPERED = "NETWORK_SIM: wss_sim: historical data preppered"
