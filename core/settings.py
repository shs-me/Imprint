from enum import CONTINUOUS, UNIQUE, IntEnum, verify
from multiprocessing.synchronize import Event, Semaphore
from typing import Protocol, TypedDict


class SegmentsType(TypedDict):
    subclasses: str


@verify(CONTINUOUS, UNIQUE)
class ClusterHeaders(IntEnum):
    Open, High, Low, Close, Volume = 0, 1, 2, 3, 4
    Time, Delta, CountTrade, _HeadersCount = 5, 6, 7, 8


@verify(CONTINUOUS, UNIQUE)
class SpaceCoords(IntEnum):
    IDYmin, IDXmin, IDYmax, IDXmax, IDY, IDX, _CoordsCount = 0, 1, 2, 3, 4, 5, 6


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
    _W = 1 * 7 * 24 * 60 * 60 * 10000


class CoreResources(Protocol):
    parsing_event: Event
    logic_event: Event
    general_event: Event
    sc_sem: Semaphore
