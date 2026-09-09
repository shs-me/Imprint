"""Enumerations, flags, and structural constant definitions."""

from enum import CONTINUOUS, UNIQUE, IntEnum, IntFlag, auto, verify
from multiprocessing import Process
from typing import Any, TypedDict


class DumpMSG(TypedDict):
    timestamp: str
    type: str
    message: str
    traceback: list[str]
    locals: dict[str, Any]


class ProcsData(TypedDict):
    """Typed dictionary representing managed worker process state and metadata."""

    proc_name: str
    task_id: int
    proc: Process


@verify(CONTINUOUS, UNIQUE)
class ProcsIds(IntEnum):
    streaming, engine, executing = 0, auto(), auto()


class KwgsKeys(IntEnum):
    """Key identifiers for inter-process parameter dictionaries."""

    Configs, Segments, MainTools = auto(), auto(), auto()
    ShmName, ShmSize = auto(), auto()


@verify(CONTINUOUS, UNIQUE)
class LogLevel(IntEnum):
    INFO, SUCCESS, WARNING, ERROR, CRITICAL = 0, auto(), auto(), auto(), auto()


class StatusCodes(IntEnum):
    """Process status codes and bitmask enumeration.
    64-bit status code flags representing process lifecycle states, pipeline warnings, and errors."""

    label: str  # pyright: ignore[reportUninitializedInstanceVariable]

    def __new__(cls, sc_label: str):
        """Dynamically constructs single-bit bitmask flag integer for each status enum entry."""

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
    HAVE_LOG = "Have log"
    BIG_LOG_SIZE = "Log size too big"
    RING_BUFFER_LOG_STREAM_OVERFLOW = "LogStream buffer overflow"
    # - - -
    # Engine
    INVALID_DATA = "Invalid data (0 > price or qty or timestamp)"
    FP_IDY_FILLED = "(FP rows < ID-Y) or (ID-Y <= 0), re-init fp ..."
    FP_IDX_FILLED = "FP cols < ID-X, re-init fp ..."
    FP_RE_INIT = "FP re-initialized"
    ANALYSIS_LAG_MORE_SAFE_LAG = "Analysis lag > safe lag limit"
    # WSS/SIM
    BIG_RAW_DATA = "Size/Len raw_data > data_cell_size_in_ring_buffer"
    DATA_PREPARED = "Trades data, prepared"
    # EXECUTION
    LOSS_MORE_LIMIT = "Balance >= max loss limit"
    QTY_LESS_LIMIT = "Nominal qty <= min order size"
    ORDER_LIMIT = "Active Orders > order limit"


class Timeframe(IntEnum):
    """Bar aggregation time intervals in milliseconds."""

    S30 = 30 * 1000
    M1 = 1 * 60 * 1000
    M5 = 5 * 60 * 1000
    M15 = 15 * 60 * 1000
    M30 = 30 * 60 * 1000
    H1 = 1 * 60 * 60 * 1000


@verify(CONTINUOUS, UNIQUE)
class CachedStatesData(IntEnum):
    """Index mapping for cached static Footprint indicators array."""

    VWAP, UPPER_BB, LOWER_BB = 0, auto(), auto()
    POC_FP, VAH_FP, VAL_FP = auto(), auto(), auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class OrderBook(IntEnum):
    """Index mapping for internal order book array columns."""

    timestamp, orderParam, clientOrderID = 0, auto(), auto()
    nPrice, nQty = auto(), auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class EquityHeaders(IntEnum):
    Timestamp, Open, High, Low, Close = 0, auto(), auto(), auto(), auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class TradeParam(IntEnum):
    """Index mapping for trade execution record array columns."""

    nPrice, nQty, timestamp, order_param = 0, auto(), auto(), auto()
    nCommission, order_id, client_order_id = auto(), auto(), auto()
    nMAE, nMFE = auto(), auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    """Index mapping for Bar Header array columns."""

    # Footprint Writer
    Open, High, Low, Close = 0, auto(), auto(), auto()
    Volume, Delta, CVD = auto(), auto(), auto()
    VWAP, VWAP_UPPER_BAND, VWAP_LOWER_BAND = auto(), auto(), auto()
    OpenTime, LastTradeTime = auto(), auto()
    CountTrade = auto()
    # Footprint Reader
    ATR, PARK = auto(), auto()
    POC, VAH, VAL = auto(), auto(), auto()
    POC_FP, VAH_FP, VAL_FP = auto(), auto(), auto()
    ConstantCount = auto()


class StateFlags(IntFlag):
    """Bitmask flags marking Footprint, Bar, Indicator, and Auction market states."""

    # Footprint States
    # Footprint: RealTime
    BID_DELTA_DOMINATION_FP, ASK_DELTA_DOMINATION_FP = auto(), auto()
    # Footprint: Static
    VWAP_FP, UPPER_BAND_FP, LOWER_BAND_FP = auto(), auto(), auto()
    POC_FP, VAL_FP, VAH_FP = auto(), auto(), auto()
    # Bar States
    OPEN, CLOSE, HIGH, LOW = auto(), auto(), auto(), auto()
    # Bar: Indicators
    POC_BAR, VAL_BAR, VAH_BAR = auto(), auto(), auto()
    # Bar: Context
    UNFINISHED_AUCTION, FINISHED_AUCTION = auto(), auto()
    ABSORPTION, EXHAUSTION = auto(), auto()
    # Bid/Ask States
    DELTA_DOMINATION, ZERO_PRINT, IMBALANCE = auto(), auto(), auto()
    # Cluster States
    BIG_TRADE = auto()


class OrderFlag(IntFlag):
    """Bitmask flags specifying order side, type, status, and position parameters."""

    # Position Side
    LONG, SHORT = auto(), auto()
    # Side
    BUY, SELL = auto(), auto()
    # Type
    LIMIT, MARKET = auto(), auto()
    MARKET_TRIGGER, LIMIT_TRIGGER = auto(), auto()
    # Status
    NEW, CANCEL, FILLED, CANCELED = auto(), auto(), auto(), auto()


class ReInitFlag(IntFlag):
    session, idx, idy = auto(), auto(), auto()


class PositionFSM(IntFlag):
    PENDING, OPEN, CLOSE, EMPTY = auto(), auto(), auto(), auto()
