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

    # General
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
    UNVALID_DATA = "_update_cells[ aggTradeData[price,qty or timestamp] < 0 ]"
    FP_IDX_FILLED = "FootprintWriter: update: array[fpCols] < idx or idx < 0"
    FP_IDY_FILLED = "FootprintWriter: update: array[fpLines] < idy or idy < 0"
    # Logic
    ANALYSIS_LAG_MORE_SAFE_LAG = (
        "Analysis lag[endReadingTime - StartReadingTime] > AnalysisSafeLagMs"
    )
    # PARSING/LOGIC
    FP_RE_INIT = "Footprint re-initializated"
    # WSS/SIM
    BIG_RAW_DATA = (
        "wss: _set_raw_data: size/len raw_data > data_cell_size_in_ring_buffer"
    )
    DATA_PREPPERED = "wss_sim: historical data preppered"
    # EXECUTION
    LOSS_MORE_LIMIT = "balance >= max loss limit"
    QTY_LESS_LIMIT = "qtyUSDT <= min order size in usdt"
