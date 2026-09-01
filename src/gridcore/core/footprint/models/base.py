from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, SupportsIndex, cast, overload

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from .converter import Converter

T_SLICE = slice[SupportsIndex | None]
T_INDEX = SupportsIndex

T_1D = T_SLICE | T_INDEX

T_IDY = T_1D
T_IDX = T_1D

T_FP_MODE = Literal["base", "state"]

T_FP = T_FP_MODE | tuple[T_FP_MODE, T_IDY] | tuple[T_FP_MODE, T_IDY, T_IDX]
T_VP = T_FP_MODE | tuple[T_FP_MODE, T_IDY]
T_VA = Literal["poc", "vah", "val"]

T_PRICE = Literal["idy", "n"]
T_QTY = tuple[Literal["bid", "ask", "sum", "delta"], Literal["fp", "bar"]]


@dataclass(slots=True)
class Footprint:
    con: Converter

    __fp: NDArray[int64] = field(
        default_factory=lambda: np.array([0], dtype=int64), init=False
    )
    __fp_state: NDArray[int64] = field(
        default_factory=lambda: np.array([0], dtype=int64), init=False
    )
    __fp_state_cache: NDArray[int64] = field(
        default_factory=lambda: np.array([0], dtype=int64), init=False
    )

    headers: NDArray[int64] = field(init=False)
    bar: Bar = field(init=False)
    vp: VolumeProfile = field(init=False)

    def __post_init__(self) -> None:
        self.bar = Bar(self)
        self.vp = VolumeProfile(self)

        self.headers = np.zeros(
            shape=(self.con.chart_range * self.con.bar_count, c.BH_ConstantCount),
            dtype=int64,
        )

    @overload
    def __getitem__(self, i: tuple[T_FP_MODE, T_INDEX, T_INDEX], /) -> int64: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, i: T_FP, /) -> NDArray[int64]: ...

    def __getitem__(self, i: T_FP, /):
        if isinstance(i, tuple):
            if len(i) == 3:
                if isinstance(i[1], SupportsIndex) and isinstance(i[2], SupportsIndex):
                    if i[0] == "base":
                        return self.__fp[i[1], i[2]]
                    else:
                        return self.__fp_state[i[1], i[2]]
                else:
                    if i[0] == "base":
                        return self.__fp[i[1], i[2]]
                    else:
                        return self.__fp_state[i[1], i[2]]
            else:
                return self.__fp[i[1]] if (i[0] == "base") else self.__fp_state[i[1]]
        else:
            return self.__fp if (i == "base") else self.__fp_state

    def __setitem__(self, i: tuple[T_FP_MODE, NDArray[int64]]) -> None:
        if i[0] == "base":
            self.__fp = i[1]
        else:
            self.__fp_state = i[1]


@dataclass
class Bar:
    _fp: Footprint


@dataclass(slots=True)
class VolumeProfile:
    _fp: Footprint

    __idx: int = field(init=False)
    __plike: PriceLike = field(init=False)

    def __post_init__(self) -> None:
        self.__idx = self._fp.con.idxVP
        self.__plike = PriceLike(self._fp.con)

    @overload
    def __getitem__(
        self, i: T_FP_MODE | tuple[T_FP_MODE, T_SLICE], /
    ) -> NDArray[int64]: ...
    @overload
    def __getitem__(self, i: tuple[T_FP_MODE, T_INDEX], /) -> int64: ...
    @overload
    def __getitem__(self, i: T_VA, /) -> PriceLike: ...

    def __getitem__(self, i: T_VP | T_VA, /):
        if isinstance(i, tuple):
            if isinstance(i[1], slice):
                return self._fp[i[0], i[1], self.__idx]
            else:
                return self._fp[i[0], i[1], self.__idx]

        elif i == "base" or i == "state":
            return self._fp[i, :, self.__idx]

        elif i == "poc":
            return self.__plike

        elif i == "vah":
            return self.__plike

        else:
            return self.__plike


@dataclass(slots=True)
class PriceLike:
    _con: Converter

    __nPrice: int64 = field(default=int64(0), init=False)

    def __setitem__(self, nPrice: int64) -> None:
        self.__nPrice = nPrice

    @overload
    def __getitem__(self, item: Literal["n"], /) -> int64: ...
    @overload
    def __getitem__(self, item: Literal["idy"], /) -> int64: ...
    def __getitem__(self, item: T_PRICE, /):
        if item == "n":
            return self.__nPrice
        else:
            return cast(int64, self._con.to_idy(self.__nPrice))


@dataclass(slots=True)
class QtyLike:
    _fp: Footprint

    __idy: int64 = field(default=int64(0), init=False)
    __idx: int64 = field(default=int64(0), init=False)
    __bids_slice: slice = field(default=slice(None, None, 2), init=False)
    __asks_slice: slice = field(default=slice(1, None, 2), init=False)

    def __setitem__(self, idy: int64, idx: int64) -> None:
        self.__idy, self.__idx = idy, idx

    def __getitem__(self, item: T_QTY, /) -> int64:
        ask_lvl = self.__asks_slice if item[1] == "fp" else self.__idx
        bid_lvl = self.__bids_slice if item[1] == "fp" else self.__idx

        if item[0] == "bid":
            return self.__bids(bid_lvl)
        elif item[0] == "ask":
            return self.__asks(ask_lvl)
        elif item[0] == "sum":
            return self.__bids(bid_lvl) + self.__asks(ask_lvl)
        else:
            return self.__bids(bid_lvl) - self.__asks(ask_lvl)

    def __bids(self, key: slice | int64) -> int64:
        return self._fp.vp["base", self.__idy]

    def __asks(self, key: slice | int64) -> int64:
        return self._fp.vp["base", self.__idy]
