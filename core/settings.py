from enum import CONTINUOUS, UNIQUE, IntEnum, auto, verify
from multiprocessing.synchronize import Event, Semaphore
from typing import Protocol


class CoreResources(Protocol):
    parsing_event: Event
    logic_event: Event
    execution_event: Event
    general_event: Event
    sc_sem: Semaphore


class StateFlags(IntEnum):
    def __new__(cls, giglet: None):
        value = 1 << len(cls.__members__)
        obj = int.__new__(cls, value)
        obj._value_ = value
        return obj

    # Footprint States
    # Footprint: RealTime
    BID_DELTA_DOMINATION_FP = None
    ASK_DELTA_DOMINATION_FP = None
    # Footprint: Timeout
    VWAP = None
    POC_FP = None
    VA_MIN_FP = None
    VA_MAX_FP = None

    # Bar States
    OPEN = None
    CLOSE = None
    HIGH = None
    LOW = None
    # Bar: Indicators
    POC_BAR = None
    VA_MIN_BAR = None
    VA_MAX_BAR = None
    # Bar: Context
    UNFINISHED_AUCTION = None
    ABSORPTION = None
    EXHAUSTION = None

    # Bid/Ask States
    DELTA_DOMINATION = None
    ZERO_PRINT = None
    IMBALANCE = None

    # Cluster States
    BIG_TRADE = None


class SignalSetup(IntEnum):
    BUY, SELL = 0, 1
    OPEN, CLOSE = 0, 1
    MARKET, LIMIT = 0, 1


@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    Open, High, Low, Close, Time = 0, auto(), auto(), auto(), auto()
    Volume, Delta, CVD = auto(), auto(), auto()
    VWAP, VWAP_Weights, VWAP_PWeights = auto(), auto(), auto()
    CountTrade = auto()
    _HeadersCount = auto()


@verify(CONTINUOUS, UNIQUE)
class SpaceCoords(IntEnum):
    IDYmin, IDXmin, IDYmax, IDXmax = 0, auto(), auto(), auto()
    _CoordsCount = auto()


class ChartInterval(IntEnum):
    """
    Constant prefixs designations:
        "S": second
        "M": minute
        "H: hour
        "D": day
        "W": week

    All constant convert to millisecond.
    """

    _30S = 30 * 1000
    _M = 1 * 60 * 1000
    _5M = 5 * 60 * 1000
    _15M = 15 * 60 * 1000
    _30M = 30 * 60 * 1000
    _H = 1 * 60 * 60 * 1000
    _4H = 4 * 60 * 60 * 1000
    _8H = 8 * 60 * 60 * 1000
    _12H = 12 * 60 * 60 * 1000
    _D = 1 * 24 * 60 * 60 * 1000
    _W = 1 * 7 * 24 * 60 * 60 * 1000
