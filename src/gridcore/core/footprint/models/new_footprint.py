from __future__ import annotations

from dataclasses import dataclass, field
from typing import override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from .base import Chart, FPArray, PriceLike, ProfileLike, QtyLike
from .converter import Converter
from .new_bar import Bar


@dataclass(slots=True)
class Footprint(Chart):
    con: Converter

    base: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    state: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)

    state_cache: NDArray[int64] = field(init=False)
    headers: NDArray[int64] = field(init=False)
    bar: Bar = field(init=False)
    vp: VolumeProfile = field(init=False)
    dp: DeltaProfile = field(init=False)

    __plike: PriceLike = field(init=False)

    def __post_init__(self) -> None:
        self.state_cache = np.zeros((c.CSD_ConstantCount,), dtype=int64)
        self.headers = np.zeros(
            shape=(self.con.chart_range * self.con.bar_count, c.BH_ConstantCount),
            dtype=int64,
        )
        self.bar = Bar(self)
        self.vp = VolumeProfile(self.con.idxVP, self)
        self.dp = DeltaProfile(self.con.idxDP, self)
        self.__plike = PriceLike(self.con, Qty(self))

    @property
    def vwap(self) -> PriceLike:
        return self.__plike[self.state_cache[c.CSD_POC_FP]]

    @property
    def vwap_up_band(self) -> PriceLike:
        return self.__plike[self.state_cache[c.CSD_UPPER_BB]]

    @property
    def vwap_low_band(self) -> PriceLike:
        return self.__plike[self.state_cache[c.CSD_LOWER_BB]]


@dataclass(slots=True)
class VolumeProfile(ProfileLike):
    _fp: Footprint

    __plike: PriceLike = field(init=False)

    def __post_init__(self) -> None:
        self.__plike = PriceLike(self._fp.con, Qty(self._fp))

    @property
    def base(self) -> VolumeProfile:
        self.__arr = self._fp.base
        return self

    @property
    def state(self) -> VolumeProfile:
        self.__arr = self._fp.base
        return self

    @property
    def poc(self) -> PriceLike:
        return self.__plike[self._fp.state_cache[c.CSD_POC_FP]]

    @property
    def vah(self) -> PriceLike:
        return self.__plike[self._fp.state_cache[c.CSD_VAH_FP]]

    @property
    def val(self) -> PriceLike:
        return self.__plike[self._fp.state_cache[c.CSD_VAL_FP]]


@dataclass(slots=True)
class DeltaProfile(ProfileLike):
    _fp: Footprint

    @property
    def base(self) -> DeltaProfile:
        self.__arr = self._fp.base
        return self

    @property
    def state(self) -> DeltaProfile:
        self.__arr = self._fp.base
        return self


@dataclass(slots=True)
class Qty(QtyLike):
    _fp: Footprint

    @override
    def __getitem__(self, idy: int64) -> Qty:
        self.__idy = idy
        return self

    @property
    def delta(self) -> int64:
        return self._fp.dp.base[self.__idy]

    @property
    def sum(self) -> int64:
        return self._fp.vp.base[self.__idy]

    @property
    def bid(self) -> int64:
        return (self.sum + self.delta) // 2

    @property
    def ask(self) -> int64:
        return (self.sum - self.delta) // 2
