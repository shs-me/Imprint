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
    RUN = "Running"
    STOP = "Stopping"
    EXIT = "Exit"
    SLEEP = "Sleeping"
    WAKE_UP = "Wake up"
    COMPLETE = "Complete and exit"
    ERROR = "ERROR more info in 'exc_dump'"
    GC_COLLECT = "Collect garbage"
    # - - -
    # PARSING
    UNVALID_DATA = "Unvalid data (0 > price or qty or timestamp)"
    FP_IDX_FILLED = "Footprint X axis filled or (IDX < 0)"
    FP_IDY_FILLED = "Footprint Y axis filled"
    # Logic
    ANALYSIS_LAG_MORE_SAFE_LAG = "Analysis lag > safe lag limit"
    # PARSING/LOGIC
    FP_RE_INIT = "Footprint re-initializated"
    # WSS/SIM
    BIG_RAW_DATA = "Size/Len raw_data > data_cell_size_in_ring_buffer"
    DATA_PREPPERED = "Data preppered"
    # EXECUTION
    LOSS_MORE_LIMIT = "Balance >= max loss limit"
    QTY_LESS_LIMIT = "Nominal qty <= min order size"
