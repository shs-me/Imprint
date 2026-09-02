from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, overload, override

import numpy as np
from numpy import float64, int64

from ... import constant as c
from .base import Chart, FPArray, PriceLike, ProfileLike, QtyLike

if TYPE_CHECKING:
    from .typing import T_ASK, T_BAR, T_BID, T_IDY, T_INDEX, T_SLICE

PARK_FACTOR: int = 1.0 / (4.0 * np.log(2.0))


@dataclass(slots=True)
class Bar:
    _fp: Chart

    ind: Indicators = field(init=False)
    vp: VolumeProfile = field(init=False)
    dp: DeltaProfile = field(init=False)

    idx: int | int64 = field(default=0, init=False)
    idXbid: int | int64 = field(default=0, init=False)
    bar_id: int | int64 = field(default=0, init=False)
    bar_side: T_BID | T_ASK = field(default=0, init=False)

    __blike: BarLike = field(default_factory=lambda: BarLike(), init=False)

    def __post_init__(self) -> None:
        self.ind = Indicators(self)
        self.vp = VolumeProfile(self._fp.con.idxVP, self)
        self.dp = DeltaProfile(self._fp.con.idxDP, self)

    def __getitem__(self, idx: int | int64) -> Bar:
        self.idx = idx
        self.idXbid = self.idx & ~1
        self.bar_id = self.idXbid // 2
        self.bar_side = 1 if self.idx != self.idXbid else 0
        return self

    def _get_header(self, header: int) -> int64:
        return self._fp.headers[self.bar_id, header]

    @property
    def base(self) -> BarLike:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        self.__blike[None] = self._fp.base[
            idYmin : idYmax + 1, self.idXbid : self.idXbid + 2
        ]
        return self.__blike

    @property
    def state(self) -> BarLike:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        self.__blike[None] = self._fp.state[
            idYmin : idYmax + 1, self.idXbid : self.idXbid + 2
        ]
        return self.__blike


@dataclass(slots=True)
class BarLike:
    __blike: BidLike = field(default_factory=lambda: BidLike(), init=False)
    __alike: AskLike = field(default_factory=lambda: AskLike(), init=False)

    __arr: FPArray = field(init=False)

    def __setitem__(self, key: None, arr: FPArray) -> None:
        self.__arr = arr

    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_ASK | T_BID], /) -> int64: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: T_BAR, /) -> FPArray: ...
    def __getitem__(self, key: T_BAR, /):  # pyright: ignore[reportInconsistentOverload]
        return self.__arr[key]

    @property
    def all(self) -> BarLike:
        return self

    @property
    def bid(self) -> BidLike:
        self.__blike[None] = self.__arr[:, 0]
        return self.__blike

    @property
    def ask(self) -> AskLike:
        self.__alike[None] = self.__arr[:, 1]
        return self.__alike


@dataclass(slots=True)
class BidLike:
    i: FPArray = field(init=False)

    def __setitem__(self, key: None, arr: FPArray) -> None:
        self.i = arr

    @overload
    def __getitem__(self, key: T_INDEX) -> int64: ...
    @overload
    def __getitem__(self, key: T_SLICE) -> FPArray: ...
    def __getitem__(self, key: T_IDY):  # pyright: ignore[reportInconsistentOverload]
        return self.i[key]


@dataclass(slots=True)
class AskLike(BidLike): ...


@dataclass(slots=True)
class Indicators:
    _bar: Bar

    __plike: PriceLike = field(init=False)
    __bar: Bar = field(init=False)

    def __post_init__(self) -> None:
        self.__plike = PriceLike(self._bar._fp.con, Qty(self._bar))

    @property
    def open(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_Open)]

    @property
    def high(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_High)]

    @property
    def low(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_Low)]

    @property
    def close(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_Close)]

    @property
    def open_time(self) -> int64:
        return self.__bar._get_header(header=c.BH_Time)

    @property
    def last_trade_time(self) -> int64:
        return self.__bar._get_header(header=c.BH_LastTradeTime)

    @property
    def volume(self) -> int64:
        return self.__bar._get_header(c.BH_Volume)

    @property
    def avg_volume(self) -> int64:
        bar_min, bar_max = max(0, self.__bar.bar_id - 20), self.__bar.bar_id + 1
        return int64(self._bar._fp.headers[bar_min:bar_max, c.BH_Volume].mean())

    @property
    def trade_count(self) -> int64:
        return self.__bar._get_header(c.BH_CountTrade)

    @property
    def avg_trade_count(self) -> int64:
        bar_min, bar_max = max(0, self.__bar.bar_id - 20), self.__bar.bar_id + 1
        return self._bar._fp.headers[bar_min:bar_max, c.BH_CountTrade].mean()

    @property
    def avg_trade_size(self) -> int64:
        return self.volume // self.trade_count

    @property
    def delta(self) -> int64:
        return self.__bar._get_header(c.BH_Delta)

    @property
    def delta_ratio(self) -> float:
        return self.delta / self.volume

    @property
    def cvd(self) -> int64:
        return self.__bar._get_header(c.BH_CVD)

    @property
    def range(self) -> int64:
        return self.high.n - self.low.n

    @property
    def range_percent(self) -> float64:
        return self.high.n / self.low.n - 1

    @property
    def change(self) -> int64:
        return self.close.n - self.open.n

    @property
    def change_percent(self) -> float64:
        open, close = self.open.n, self.close.n
        return (close / open - 1) if (close >= open) else -abs(open / close - 1)

    @property
    def atr(self) -> int64:
        return self.__bar._get_header(c.BH_ATR)

    @property
    def atr_percent(self) -> float64:
        close, atr = self.close.n, self.atr
        return ((atr + close) / close) - 1

    @property
    def parkinson_percent(self) -> float64:
        return np.sqrt((self.__bar._get_header(c.BH_PARK) / c.VAR_SCALE) * PARK_FACTOR)

    @property
    def fp_vwap(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_VWAP)]

    @property
    def fp_vwap_up_band(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_VWAP_UPPER_BAND)]

    @property
    def fp_vwap_low_band(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_VWAP_LOWER_BAND)]

    @property
    def fp_poc(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_POC_FP)]

    @property
    def fp_vah(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_VAH_FP)]

    @property
    def fp_val(self) -> PriceLike:
        return self.__plike[self.__bar._get_header(c.BH_VAL_FP)]


@dataclass(slots=True)
class VolumeProfile(ProfileLike):
    _bar: Bar

    __plike: PriceLike = field(init=False)

    def __post_init__(self) -> None:
        self.__plike = PriceLike(self._bar._fp.con, Qty(self._bar))

    @property
    def base(self) -> VolumeProfile:
        bar = self._bar.base
        self.__arr = bar.bid.i + bar.ask.i  # pyright: ignore[reportAttributeAccessIssue]
        return self

    @property
    def poc(self) -> PriceLike:
        return self.__plike[self._bar._get_header(c.BH_POC)]

    @property
    def vah(self) -> PriceLike:
        return self.__plike[self._bar._get_header(c.BH_VAH)]

    @property
    def val(self) -> PriceLike:
        return self.__plike[self._bar._get_header(c.BH_VAL)]


@dataclass(slots=True)
class DeltaProfile(ProfileLike):
    _bar: Bar

    @property
    def base(self) -> DeltaProfile:
        bar = self._bar.base
        self.__arr = bar.bid.i - bar.ask.i  # pyright: ignore[reportAttributeAccessIssue]
        return self


@dataclass(slots=True)
class Qty(QtyLike):
    _bar: Bar
    __blike: BarLike = field(init=False)

    @override
    def __getitem__(self, idy: int64) -> Qty:
        self.__idy = idy
        self.__blike = self._bar.base
        return self

    @property
    def volume(self) -> int64:
        return self.__blike.all[self.__idy, self._bar.bar_side]

    @property
    def delta(self) -> int64:
        return self.bid - self.ask

    @property
    def sum(self) -> int64:
        return self.bid + self.ask

    @property
    def bid(self) -> int64:
        return self.__blike.bid[self.__idy]

    @property
    def ask(self) -> int64:
        return self.__blike.ask[self.__idy]
