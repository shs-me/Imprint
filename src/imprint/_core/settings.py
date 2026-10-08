"""Enumerations, flags, and structural constant definitions."""

from enum import CONTINUOUS, UNIQUE, IntEnum, IntFlag, auto, verify


@verify(CONTINUOUS, UNIQUE)
class ProcsIds(IntEnum):
    """Process identifiers for the system architecture."""

    streaming = 0
    engine = auto()
    executing = auto()


class KwgsKeys(IntEnum):
    """Key identifiers for inter-process parameter dictionaries."""

    Configs = auto()
    SegmentConfigs = auto()
    Segments = auto()
    MainTools = auto()
    ShmName = auto()
    ShmSize = auto()


@verify(CONTINUOUS, UNIQUE)
class LogLevel(IntEnum):
    """Severity levels for system logging and diagnostics."""

    INFO = 0
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class StatusCodes(IntEnum):
    """Process status codes and bitmask enumeration.

    64-bit status code flags representing process lifecycle states, pipeline
    warnings, and errors.
    """

    label: str  # pyright: ignore[reportUninitializedInstanceVariable]

    def __new__(cls, sc_label: str):
        """Dynamically construct single-bit bitmask flag integer for each status enum entry.

        Parameters
        ----------
        sc_label : str
            Human-readable description corresponding to the status flag.

        Returns
        -------
        StatusCodes
            Instantiated enum member with an auto-assigned bitmask integer value.

        Raises
        ------
        ValueError
            If the number of enum members reaches or exceeds 64, overflowing the
            64-bit integer limit.
        """

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
    TERMINATE = "Terminate"
    RESET = "Reset"
    COMPLETE = "Complete"
    ERROR = "ERROR more info in 'exc_dump'"
    GC_COLLECT = "Collect garbage"
    HAVE_LOG = "Have log"
    BIG_LOG_SIZE = "Log size too big"
    RING_BUFFER_LOG_STREAM_OVERFLOW = "LogStream buffer overflow"
    INVALID_DATA = "Invalid data"
    DECODE_ERROR = "Decode error, more info in exc dump"
    ENCODE_ERROR = "Encode error, more info in exc dump"
    FP_IDY_FILLED = "(FP rows < ID-Y) or (ID-Y <= 0), re-init fp ..."
    FP_IDX_FILLED = "FP cols < ID-X, re-init fp ..."
    FP_RE_INIT = "FP re-initialized"
    ANALYSIS_LAG_MORE_SAFE_LAG = "Analysis lag > safe lag limit"
    BIG_RAW_DATA = "Size/Len raw_data > data_cell_size_in_ring_buffer"
    BIG_GAP = "Big Gap, gap > buffer capacity"
    DATA_PREPARED = "Trades data, prepared"
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
class OrderBook(IntEnum):
    """Index mapping for internal order book array columns."""

    timestamp = 0
    orderParam = auto()
    clientOrderID = auto()
    nPrice = auto()
    nQty = auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class EquityHeaders(IntEnum):
    """Index mapping for equity candlestick array columns."""

    Timestamp = 0
    Open = auto()
    High = auto()
    Low = auto()
    Close = auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class TradeParam(IntEnum):
    """Index mapping for trade execution record array columns."""

    nPrice = 0
    nQty = auto()
    timestamp = auto()
    order_param = auto()
    nCommission = auto()
    order_id = auto()
    client_order_id = auto()
    nMAE = auto()
    nMFE = auto()
    planned_tp = auto()
    planned_sl = auto()
    ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    """Index mapping for Bar Header array columns."""

    # Footprint Writer
    Open = 0
    High = auto()
    Low = auto()
    Close = auto()
    Volume = auto()
    Delta = auto()
    CVD = auto()
    VWAP = auto()
    VWAP_UPPER_BAND = auto()
    VWAP_LOWER_BAND = auto()
    OpenTime = auto()
    LastTradeTime = auto()
    CountTrade = auto()
    # Footprint Reader
    ATR = auto()
    PARK = auto()
    MA_VOL = auto()
    MA_COUNT_TRADE = auto()
    MA_ATS = auto()
    POC = auto()
    VAH = auto()
    VAL = auto()
    POC_FP = auto()
    VAH_FP = auto()
    VAL_FP = auto()
    ConstantCount = auto()


class StateFlags(IntFlag):
    """Bitmask flags marking Footprint, Bar, Indicator, and Auction market states."""

    # Footprint States
    # Footprint: RealTime
    BID_DELTA_DOMINATION_FP = auto()
    ASK_DELTA_DOMINATION_FP = auto()
    # Footprint: Static
    VWAP_FP = auto()
    UPPER_BAND_FP = auto()
    LOWER_BAND_FP = auto()
    POC_FP = auto()
    VAL_FP = auto()
    VAH_FP = auto()
    # Bar States
    OPEN = auto()
    CLOSE = auto()
    HIGH = auto()
    LOW = auto()
    # Bar: Indicators
    POC_BAR = auto()
    VAL_BAR = auto()
    VAH_BAR = auto()
    # Bar: Context
    UNFINISHED_AUCTION = auto()
    FINISHED_AUCTION = auto()
    ABSORPTION = auto()
    EXHAUSTION = auto()
    # Bid/Ask States
    DELTA_DOMINATION = auto()
    ZERO_PRINT = auto()
    IMBALANCE = auto()
    # Cluster States
    BIG_CLUSTER = auto()


class OrderFlag(IntFlag):
    """Bitmask flags specifying order side, type, status, and position parameters."""

    # Position Side
    LONG = auto()
    SHORT = auto()
    # Side
    BUY = auto()
    SELL = auto()
    # Type
    LIMIT = auto()
    MARKET = auto()
    MARKET_TRIGGER = auto()
    LIMIT_TRIGGER = auto()
    # Status
    NEW = auto()
    CANCEL = auto()
    FILLED = auto()
    CANCELED = auto()


class ReInitFlag(IntFlag):
    """Bitmask flags specifying re-initialization scopes for pipeline state."""

    session = auto()
    idx = auto()
    idy = auto()


class PositionFSM(IntFlag):
    """Finite state machine bitmask flags for trading position lifecycle states."""

    PENDING = auto()
    OPEN = auto()
    CLOSE = auto()
    EMPTY = auto()
