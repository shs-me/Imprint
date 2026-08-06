"""Enumerations, flags, and structural constant definitions."""

from enum import CONTINUOUS, UNIQUE, IntEnum, IntFlag, auto, verify
from multiprocessing import Process
from typing import TypedDict


class DataStreamProc(int):
    pass


class ParsingProc(int):
    pass


class LogicProc(int):
    pass


class ExecutionProc(int):
    pass


class ProcsData(TypedDict):
    """Typed dictionary representing managed worker process state and metadata."""

    proc_name: str
    task_id: int
    proc: Process


class KwgsKeys(IntEnum):
    """Key identifiers for inter-process parameter dictionaries."""

    Configs, Segments, MainTools = auto(), auto(), auto()
    ShmName, ShmSize = auto(), auto()


class StatusCodes(IntEnum):
    """Process status codes and bitmask enumeration.
    64-bit status code flags representing process lifecycle states, pipeline warnings, and errors."""

    label: str

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
    HAVE_TEXT = ""
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
    ORDER_LIMIT = "Active Orders > order limit"


class StateFlags(IntFlag):
    """Bitmask flags marking Footprint, Bar, Indicator, and Auction market states."""

    # Footprint States
    # Footprint: RealTime
    BID_DELTA_DOMINATION_FP, ASK_DELTA_DOMINATION_FP = auto(), auto()
    # Footprint: Static
    VWAP, UPPER_BB, LOWER_BB = auto(), auto(), auto()
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
    MARKET_TRIGER, LIMIT_TRIGER = auto(), auto()
    # Status
    NEW, FILLED, CANCELED = auto(), auto(), auto()
    OCO = auto()


class Timeframe(IntEnum):
    """Bar aggregation time intervals in milliseconds."""

    _30S = 30 * 1000
    _M = 1 * 60 * 1000
    _5M = 5 * 60 * 1000
    _15M = 15 * 60 * 1000
    _30M = 30 * 60 * 1000
    _H = 1 * 60 * 60 * 1000


@verify(CONTINUOUS, UNIQUE)
class CachedStatesData(IntEnum):
    """Index mapping for cached static Footprint indicators array."""

    VWAP, UPPER_BB, LOWER_BB = 0, auto(), auto()
    POC_FP, VAH_FP, VAL_FP = auto(), auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class OrderBook(IntEnum):
    """Index mapping for internal order book array columns."""

    timestamp, orderParam, clientOrderID = 0, auto(), auto()
    nPrice, nQty = auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class TradeParam(IntEnum):
    """Index mapping for trade execution record array columns."""

    nPrice, nQty, timestamp, orderParam = 0, auto(), auto(), auto()
    nCommission, orderID = auto(), auto()
    nMAE, nMFE = auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    """Index mapping for Bar Header array columns."""

    # Footprint Writer
    Open, High, Low, Close = 0, auto(), auto(), auto()
    Volume, Delta, CVD = auto(), auto(), auto()
    VWAP, VWAP_BB_UPPER, VWAP_BB_LOWER = auto(), auto(), auto()
    OpenTime, LastTradeTime = auto(), auto()
    CountTrade = auto()
    # Footprint Reader
    ATR, PARK = auto(), auto()
    POC, VAH, VAL = auto(), auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BarHeadersMetadata(IntEnum):
    """Index mapping for VWAP running variance calculation metadata array."""

    VWAP_W, VWAP_PW, VWAP_P2W = 0, auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class SpaceCoords(IntEnum):
    """Index mapping for modified region bounding box coordinates array."""

    IDYmin, IDXmin, IDYmax, IDXmax = 0, auto(), auto(), auto()
    _ConstantCount = auto()
