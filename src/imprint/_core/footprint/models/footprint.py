from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, final, overload, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.footprint.models.bar import Bar
from imprint._core.footprint.models.base import Chart, PriceLike, QtyLike
from imprint._core.footprint.models.converter import Converter
from imprint._core.utils import FPArray

if TYPE_CHECKING:
    from imprint._core.typing import T_INDEX, T_SLICE, T_VP


@final
@dataclass(slots=True)
class Footprint(Chart):
    con: Converter

    base: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    state: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    ctrade: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)

    headers: NDArray[int64] = field(init=False)
    bar: Bar = field(init=False)
    vp: VolumeProfile[Footprint] = field(init=False)
    dp: DeltaProfile[Footprint] = field(init=False)

    last_idx: int = field(default=0, init=False)
    __plike: PriceLike[Footprint] = field(init=False)

    def __post_init__(self) -> None:
        self.headers = np.zeros(
            shape=(self.con.total_bar_count, c.BH_ConstantCount), dtype=int64
        )
        self.headers_offset = memoryview(bytearray(8)).cast("q")

        self.bar = Bar(self)
        self.vp = VolumeProfile(self.con.idxVP, self)
        self.dp = DeltaProfile(self.con.idxDP, self)
        self.__plike = PriceLike(self.con, Qty(self))

    def _re_init_arr(  # pyright: ignore[reportUnusedFunction]
        self, base: FPArray, state: FPArray | None, ctrade: FPArray | None
    ) -> None:
        self.base = base
        if state is not None:
            self.state = state
        if ctrade is not None:
            self.ctrade = ctrade

        self.vp._re_init_arr()
        self.dp._re_init_arr()

    @property
    def last_bar(self) -> int:
        return (self.last_idx & ~1) // 2

    @property
    def vwap(self) -> PriceLike[Footprint]:
        return self.__plike[self.headers[self.last_bar, c.BH_VWAP]]

    @property
    def vwap_up_band(self) -> PriceLike[Footprint]:
        return self.__plike[self.headers[self.last_bar, c.BH_VWAP_UPPER_BAND]]

    @property
    def vwap_low_band(self) -> PriceLike[Footprint]:
        return self.__plike[self.headers[self.last_bar, c.BH_VWAP_LOWER_BAND]]


@dataclass(slots=True)
class ProfileLike[T](ABC):
    _idx: int
    _fp: Footprint

    __arr: FPArray = field(init=False)
    __base: FPArray = field(init=False)
    __state: FPArray = field(init=False)
    __plike: PriceLike[T] = field(init=False)

    def __post_init__(self) -> None:
        self.__plike = PriceLike(self._fp.con, Qty(self._fp))

    def _re_init_arr(self) -> None:
        self.__base = self._fp.base[:, self._idx]
        self.__state = self._fp.state[:, self._idx]
        self.__arr = self.__base

    @overload
    def __getitem__(self, key: T_INDEX, /) -> int64: ...
    @overload
    def __getitem__(self, key: T_SLICE, /) -> FPArray: ...
    def __getitem__(self, key: T_VP, /):  # pyright: ignore[reportInconsistentOverload]
        return self.__arr[key]

    @property
    def base(self) -> ProfileLike[T]:
        self.__arr = self.__base
        return self

    @property
    def state(self) -> ProfileLike[T]:
        self.__arr = self.__state
        return self


@dataclass(slots=True)
class VolumeProfile[T](ProfileLike[T]):
    @property
    def poc(self) -> PriceLike[T]:
        return self.__plike[self._fp.headers[self._fp.last_bar, c.BH_POC_FP]]

    @property
    def vah(self) -> PriceLike[T]:
        return self.__plike[self._fp.headers[self._fp.last_bar, c.BH_VAH_FP]]

    @property
    def val(self) -> PriceLike[T]:
        return self.__plike[self._fp.headers[self._fp.last_bar, c.BH_VAL_FP]]


@dataclass(slots=True)
class DeltaProfile[T](ProfileLike[T]): ...


@final
@dataclass(slots=True)
class Qty[T](QtyLike[T]):
    _fp: Footprint

    @override
    def __getitem__(self, idy: int64) -> Qty[T]:
        self._idy = idy
        return self

    @property
    def delta(self) -> int64:
        return self._fp.dp.base[self._idy]

    @property
    def sum(self) -> int64:
        return self._fp.vp.base[self._idy]

    @property
    def bid(self) -> int64:
        return (self.sum + self.delta) // 2

    @property
    def ask(self) -> int64:
        return (self.sum - self.delta) // 2
