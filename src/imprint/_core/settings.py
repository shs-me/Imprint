"""Enumerations for indexing, keys, and project flags"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import timedelta
from enum import CONTINUOUS, UNIQUE, IntEnum, IntFlag, StrEnum, auto, verify
from typing import final


@final
class BarTypeFlag(IntFlag):
    Time = 0
    Tick = auto()


@dataclass(slots=True)
class BarType(ABC):
    bar_type: int = field(init=False)
    bar_close_trigger: int = field(init=False)


@final
@dataclass(slots=True)
class TimeBar(BarType):
    days: int
    hours: int
    minutes: int
    seconds: int

    def __post_init__(self) -> None:
        self.bar_type = BarTypeFlag.Time
        self.bar_close_trigger = round(
            timedelta(
                days=self.days,
                hours=self.hours,
                minutes=self.minutes,
                seconds=self.seconds,
            ).total_seconds()
            * 1000
        )


@final
@dataclass(slots=True)
class TickBar(BarType):
    count: int

    def __post_init__(self) -> None:
        self.bar_type = BarTypeFlag.Tick
        self.bar_close_trigger = self.count


@final
class BarBuilder:
    time: type[TimeBar] = TimeBar
    tick: type[TickBar] = TickBar


@final
class KwgsKeys(StrEnum):
    """String keys for the main process dictionary"""

    Configs = auto()
    MemoryLayouts = auto()
    Segments = auto()
    MainTools = auto()
    ShmName = auto()
    ShmSize = auto()


@final
@verify(CONTINUOUS, UNIQUE)
class ProcsIds(IntEnum):
    """Process indices"""

    streaming = 0
    engine = auto()
    executing = auto()


@final
@verify(CONTINUOUS, UNIQUE)
class LogLevel(IntEnum):
    """Logging level indices for inter-process communication"""

    INFO = 0
    DEBUG = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@final
@verify(CONTINUOUS, UNIQUE)
class OrderBook(IntEnum):
    """Indices of pending order parameters"""

    timestamp = 0
    orderParam = auto()
    clientOrderID = auto()
    nPrice = auto()
    nQty = auto()
    ConstantCount = auto()


@final
@verify(CONTINUOUS, UNIQUE)
class EquityHeaders(IntEnum):
    """Indices of headers storing balance change history"""

    Timestamp = 0
    Open = auto()
    High = auto()
    Low = auto()
    Close = auto()
    ConstantCount = auto()


@final
@verify(CONTINUOUS, UNIQUE)
class TradeParam(IntEnum):
    """Indices of executed order parameters"""

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


@final
@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    """Indices for footprint indicators and metrics stored in each bar"""

    BaseNprice = 0
    Open = auto()
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
    CloseTime = auto()
    CountTrade = auto()
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


@final
class StatusCodes(IntFlag):
    """Process and task status flags with string descriptions"""

    label: str  # pyright: ignore[reportUninitializedInstanceVariable]

    def __new__(cls, sc_label: str):
        """Override flag creation to attach a flag documentation label"""

        value = 1 << len(cls.__members__)
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.label = sc_label
        return obj

    RUN = "Run"
    STOP = "Stop"
    EXIT = "Exit"
    TERMINATE = "Terminate"
    RESET = "Reset and Stop"
    COMPLETE = "Complete"
    ERROR = "ERROR more info in 'exc_dump'"
    GC_COLLECT = "Collect garbage"
    HAVE_LOG = "Have log"
    BIG_LOG_SIZE = "Log size too big"
    RING_BUFFER_LOG_STREAM_OVERFLOW = "LogStream buffer overflow"
    INVALID_DATA = "Invalid data"
    DECODE_ERROR = "Decode error, more info in exc dump"
    ENCODE_ERROR = "Encode error, more info in exc dump"
    PRICE_OUT_OF_BAR_BOUNDS = (
        "Price out of bar bounds: (bar_height < ID-Y) or (ID-Y <= 0)"
    )
    ANALYSIS_LAG_MORE_SAFE_LAG = "Analysis lag > safe lag limit"
    BIG_RAW_DATA = "Size/Len raw_data > data_cell_size_in_ring_buffer"
    BIG_GAP = "Big Gap, gap > buffer capacity"
    DATA_PREPARED = "Trades data, prepared"
    LOSS_MORE_LIMIT = "Balance >= max loss limit"
    QTY_LESS_LIMIT = "Nominal qty <= min order size"
    ORDER_LIMIT = "Active Orders > order limit"


@final
class StateFlags(IntFlag):
    """State flags for specific footprint matrix clusters"""

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
    # Bid/Ask States
    DELTA_DOMINATION = auto()
    ZERO_PRINT = auto()
    IMBALANCE = auto()
    # Cluster States
    BIG_CLUSTER = auto()


@final
class OrderFlag(IntFlag):
    """Order parameter state flags"""

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
    # Status
    NEW = auto()
    CANCEL = auto()
    FILLED = auto()
    CANCELED = auto()


@final
class PositionFSM(IntFlag):
    """Position finite state machine flags.
    Serve as the single source of truth for the account along with the balance"""

    PENDING = auto()
    OPEN = auto()
    CLOSE = auto()
    EMPTY = auto()
