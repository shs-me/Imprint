from enum import CONTINUOUS, UNIQUE, IntEnum, IntFlag, auto, verify
from multiprocessing.synchronize import Event, Semaphore
from typing import Protocol, TypedDict


class CoreResources(Protocol):
    parsing_event: Event
    logic_event: Event
    execution_event: Event
    general_event: Event
    sc_sem: Semaphore


class OpenPosition(TypedDict):
    positionSide: str
    openTime: str
    entryNprice: int
    nQuantity: int
    nominalNqty: int
    tempNqty: int
    nominalNcommission: int
    laverage: int
    realizedPNL: float
    realizedROI: float
    TakeProfits: dict
    StopLosses: dict


class ClosePosition(TypedDict):
    positionSide: str
    openTime: str
    closeTime: str
    entryPrice: float
    closePrice: float
    quantity: float
    nominalQty: float
    nominalCommission: float
    laverage: int
    realizedPNL: float
    realizedROI: float
    TakeProfits: dict
    StopLosses: dict


class StateFlags(IntFlag):
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
    # Position Side
    LONG, SHORT = auto(), auto()
    # Side
    BUY, SELL = auto(), auto()
    # Type
    LIMIT, MARKET = auto(), auto()
    MARKET_TRIGER, LIMIT_TRIGER = auto(), auto()
    # Status
    NEW, FILLED, CANCELED = auto(), auto(), auto()


class ChartInterval(IntEnum):
    """
    Constant prefixs designations:
        "S": second
        "M": minute
        "H: hour

    All constant convert to millisecond.
    """

    _30S = 30 * 1000
    _M = 1 * 60 * 1000
    _5M = 5 * 60 * 1000
    _15M = 15 * 60 * 1000
    _30M = 30 * 60 * 1000
    _H = 1 * 60 * 60 * 1000


@verify(CONTINUOUS, UNIQUE)
class CachedStatesData(IntEnum):
    VWAP, UPPER_BB, LOWER_BB = 0, auto(), auto()
    POC_FP, VAH_FP, VAL_FP = auto(), auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class ActiveOrders(IntEnum):
    nPrice, nQty, timestamp, orderParam = 0, auto(), auto(), auto()
    orderID = auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class TradeParam(IntEnum):
    nPrice, nQty, timestamp, orderParam = 0, auto(), auto(), auto()
    nCommission, orderID = auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BarHeaders(IntEnum):
    Open, High, Low, Close = 0, auto(), auto(), auto()
    Volume, Delta, CVD = auto(), auto(), auto()
    VWAP, VWAP_BB_UPPER, VWAP_BB_LOWER = auto(), auto(), auto()
    OpenTime, LastTradeTime = auto(), auto()
    CountTrade, ATR = auto(), auto()
    POC, VAH, VAL = auto(), auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BarHeadersMetadata(IntEnum):
    VWAP_W, VWAP_PW, VWAP_P2W = 0, auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class SpaceCoords(IntEnum):
    IDYmin, IDXmin, IDYmax, IDXmax = 0, auto(), auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class DataForMatching(IntEnum):
    nPrice, startTimestamp, endTimestamp = 0, auto(), auto()
    _ConstantCount = auto()


@verify(CONTINUOUS, UNIQUE)
class BacktestingMode(IntEnum):
    REAL_TIME_SIM, ZERO_SLEEP, NONE_STOP = 0, auto(), auto()
