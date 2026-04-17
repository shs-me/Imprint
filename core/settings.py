from enum import CONTINUOUS, UNIQUE, IntEnum, IntFlag, auto, verify
from multiprocessing.synchronize import Event, Semaphore
from typing import Protocol


class CoreResources(Protocol):
    parsing_event: Event
    logic_event: Event
    execution_event: Event
    general_event: Event
    sc_sem: Semaphore


class StateFlags(IntFlag):
    # Footprint States
    # Footprint: RealTime
    BID_DELTA_DOMINATION_FP = auto()
    ASK_DELTA_DOMINATION_FP = auto()
    # Footprint: Static
    VWAP = auto()
    UPPER_BB = auto()
    LOWER_BB = auto()
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
    BIG_TRADE = auto()


class SignalSetup(IntEnum):
    BUY, SELL = 0, 1
    OPEN, CLOSE = 0, 1
    MARKET, LIMIT = 0, 1


@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    Open, High, Low, Close, Time = 0, auto(), auto(), auto(), auto()
    Volume, Delta, CVD = auto(), auto(), auto()
    VWAP_Weights, VWAP_PWeights, VWAP_P2Weights = auto(), auto(), auto()
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
