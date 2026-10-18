from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Literal, Self, cast, final, overload

import numpy as np
from numpy import bool_, float64, int64

import imprint._core.constant as c
from imprint._core.footprint.models.base import Chart
from imprint._core.footprint.models.converter import Converter
from imprint._core.utils import FPArray
from imprint._core.utils.base import DPArray, VPArray

PARK_FACTOR: float64 = 1.0 / (4.0 * np.log(2.0))


@final
@dataclass(slots=True)
class Bar:
    """Represent a single bar and its associated indicators, volume profile, and delta profile."""

    _fp: Chart
    idXbid: int | int64

    ind: Indicators[Bar] = field(init=False)
    vp: VolumeProfile[Bar] = field(init=False)
    dp: DeltaProfile[Bar] = field(init=False)

    def __post_init__(self) -> None:
        self.ind = Indicators(self)
        self.vp = VolumeProfile(self)
        self.dp = DeltaProfile(self)

    @property
    def bar_id(self) -> int | int64:
        return self._fp.headers_offset[0] + (self.idXbid // 2)

    def _get_header(self, header: int) -> int64:
        return self._fp.headers[self.bar_id, header]

    @property
    def is_empty(self) -> bool_:
        return self._get_header(c.BH_CountTrade) == 0

    def __view_bar(self, arr: FPArray) -> FPArray:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        return arr[idYmin : idYmax + 1, self.idXbid : self.idXbid + 2]

    @property
    def base(self) -> FPArray:
        return self.__view_bar(self._fp.base)

    @property
    def state(self) -> FPArray:
        return self.__view_bar(self._fp.state)

    @property
    def ctrade(self) -> FPArray:
        return self.__view_bar(self._fp.ctrade)


@dataclass(slots=True)
class BarLike:
    _bar: Bar
    _plike_cache: dict[int, PriceLike] = field(default_factory=dict, init=False)


@final
@dataclass(slots=True)
class PriceLike:
    """Wrap price level identifiers to provide chained access to associated quantity metrics."""

    _bar: Bar

    _con: Converter = field(init=False)
    _qlike: QtyLike = field(init=False)

    n: int64 = field(default=int64(0), init=False)

    def __post_init__(self) -> None:
        self._con = self._bar._fp.con
        self._qlike = QtyLike(self._bar)

    def __getitem__(self, nPrice: int64) -> Self:
        self.n = nPrice
        return self

    @property
    def id(self) -> int64:
        return cast(int64, self._con.to_idy(self.n))

    @property
    def qty(self) -> QtyLike:
        return self._qlike[self.id]


@final
@dataclass(slots=True)
class QtyLike:
    """Provide volume, delta, bid, and ask quantities at specific price level indices for a bar."""

    _bar: Bar

    _idy: int64 = field(default=int64(0), init=False)

    def __getitem__(self, idy: int64) -> Self:
        self._idy = idy
        return self

    def volume(self, side: Literal[0, 1]) -> int64:
        return self._bar._fp.base[self._idy, side + self._bar.idXbid]

    def delta(self, local: bool = True) -> int64:
        if local:
            return self.ask(local) - self.bid(local)
        else:
            _ = self._bar._fp
            return _.base[self._idy, _.con.idxDP[0]]

    def sum(self, local: bool = True) -> int64:
        if local:
            return self.bid(local) + self.ask(local)
        else:
            _ = self._bar._fp
            return _.base[self._idy, _.con.idxVP[0]]

    def bid(self, local: bool = True) -> int64:
        if local:
            return self._bar._fp.base[self._idy, self._bar.idXbid]
        else:
            return (self.sum(local) - self.delta(local)) // 2

    def ask(self, local: bool = True) -> int64:
        if local:
            return self._bar._fp.base[self._idy, self._bar.idXbid + 1]
        else:
            return (self.sum(local) + self.delta(local)) // 2


class Headers[Tval]:
    def __init__(self, idx: int, valtype: type[Tval]) -> None:
        self.idx: int = idx
        self.is_price: bool = valtype is PriceLike

    @overload
    def __get__(self, instance: None, owner: type[BarLike]) -> Self: ...
    @overload
    def __get__(self, instance: BarLike, owner: type[BarLike]) -> Tval: ...
    def __get__(  # pyright: ignore[reportInconsistentOverload]
        self,
        instance: BarLike | None,
        owner: type[BarLike],
    ):
        if instance is None:
            return self

        value = instance._bar._get_header(self.idx)
        if self.is_price:
            plike = instance._plike_cache.get(self.idx)
            if plike is None:
                instance._plike_cache[self.idx] = plike = PriceLike(
                    instance._bar
                )

            return plike[value]
        else:
            return value


@final
@dataclass(slots=True)
class Indicators[T](BarLike):
    """Exposes technical indicators and statistical metrics for the active bar."""

    open: ClassVar[Headers[PriceLike]] = Headers(c.BH_Open, PriceLike)
    high: ClassVar[Headers[PriceLike]] = Headers(c.BH_High, PriceLike)
    low: ClassVar[Headers[PriceLike]] = Headers(c.BH_Low, PriceLike)
    close: ClassVar[Headers[PriceLike]] = Headers(c.BH_Close, PriceLike)
    fp_poc: ClassVar[Headers[PriceLike]] = Headers(c.BH_POC_FP, PriceLike)
    fp_vah: ClassVar[Headers[PriceLike]] = Headers(c.BH_VAH_FP, PriceLike)
    fp_val: ClassVar[Headers[PriceLike]] = Headers(c.BH_VAL_FP, PriceLike)
    fp_vwap: ClassVar[Headers[PriceLike]] = Headers(c.BH_VWAP, PriceLike)
    fp_vwap_up_band: ClassVar[Headers[PriceLike]] = Headers(
        c.BH_VWAP_UPPER_BAND, PriceLike
    )
    fp_vwap_low_band: ClassVar[Headers[PriceLike]] = Headers(
        c.BH_VWAP_LOWER_BAND, PriceLike
    )
    open_time: ClassVar[Headers[int64]] = Headers(c.BH_OpenTime, int64)
    last_trade_time: ClassVar[Headers[int64]] = Headers(
        c.BH_LastTradeTime, int64
    )
    volume: ClassVar[Headers[int64]] = Headers(c.BH_Volume, int64)
    ma_volume: ClassVar[Headers[int64]] = Headers(c.BH_MA_VOL, int64)
    trade_count: ClassVar[Headers[int64]] = Headers(c.BH_CountTrade, int64)
    ma_trade_count: ClassVar[Headers[int64]] = Headers(
        c.BH_MA_COUNT_TRADE, int64
    )
    ma_avg_trade_size: ClassVar[Headers[int64]] = Headers(c.BH_MA_ATS, int64)
    delta: ClassVar[Headers[int64]] = Headers(c.BH_Delta, int64)
    cvd: ClassVar[Headers[int64]] = Headers(c.BH_CVD, int64)
    atr: ClassVar[Headers[int64]] = Headers(c.BH_ATR, int64)

    @property
    def avg_trade_size(self) -> int64:
        return self.volume // self.trade_count

    @property
    def delta_ratio(self) -> float:
        return self.delta / self.volume

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
        return self.close.n / self.open.n - 1

    @property
    def atr_percent(self) -> float64:
        close = self.close.n
        return ((self.atr + close) / close) - 1

    @property
    def parkinson_percent(self) -> float64:
        return np.sqrt(
            (self._bar._get_header(c.BH_PARK) / c.VAR_SCALE) * PARK_FACTOR
        )


@final
@dataclass(slots=True)
class VolumeProfile[T](BarLike):
    """Compute volume profile aggregates for the active bar."""

    _bar: Bar

    poc: ClassVar[Headers[PriceLike]] = Headers(c.BH_POC, PriceLike)
    vah: ClassVar[Headers[PriceLike]] = Headers(c.BH_VAH, PriceLike)
    val: ClassVar[Headers[PriceLike]] = Headers(c.BH_VAL, PriceLike)

    @property
    def base(self) -> VPArray:
        bar = self._bar.base
        return bar[:, 0] + bar[:, 1]  # pyright: ignore[reportReturnType]


@final
@dataclass(slots=True)
class DeltaProfile[T](BarLike):
    """Compute delta profile aggregates (bid-ask difference) for the active bar."""

    _bar: Bar

    @property
    def base(self) -> DPArray:
        bar = self._bar.base
        return bar[:, 1] - bar[:, 0]  # pyright: ignore[reportReturnType]
