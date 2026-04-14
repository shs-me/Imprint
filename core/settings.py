from enum import CONTINUOUS, UNIQUE, IntEnum, auto, verify
from multiprocessing.synchronize import Event, Semaphore
from typing import Protocol


class StateFlags(IntEnum):
    NONE = 0
    # Footprint States
    POC_FP = 1 << 0
    VA_MIN_FP = 1 << 1
    VA_MAX_FP = 1 << 2
    # Bar States
    OPEN = 1 << 3
    CLOSE = 1 << 4
    HIGH = 1 << 5
    LOW = 1 << 6
    # Bar: Indicators
    POC_BAR = 1 << 7
    VA_MIN_BAR = 1 << 8
    VA_MAX_BAR = 1 << 9
    # Bar: Context
    UNFINISHED_AUCTION = 1 << 10
    ABSORPTION = 1 << 11
    EXHAUSTION = 1 << 12
    # Bid/Ask States
    DELTA_DOMINATION = 1 << 13
    ZERO_PRINT = 1 << 14
    IMBALANCE = 1 << 15
    # Cluster States
    BIG_TRADE = 1 << 16


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


class CoreResources(Protocol):
    parsing_event: Event
    logic_event: Event
    general_event: Event
    sc_sem: Semaphore
