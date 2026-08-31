from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, SupportsIndex, TypeAlias, cast, overload

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from .converter import Converter

T_SLICE: TypeAlias = slice[int | int64]

T_1D: TypeAlias = T_SLICE | SupportsIndex
T_IDY: TypeAlias = T_1D
T_IDX: TypeAlias = T_1D
T_2D: TypeAlias = tuple[T_IDY, T_IDX]

T_FP_MODE: TypeAlias = Literal["base", "state"]
T_VA: TypeAlias = Literal["poc", "vah", "val"]
T_PRICE: TypeAlias = Literal["idy", "n"]
T_QTY: TypeAlias = tuple[Literal["bid", "ask", "sum", "delta"], Literal["fp", "bar"]]
T_VP: TypeAlias = tuple[T_1D, T_FP_MODE] | T_VA


@dataclass(slots=True)
class Footprint:
    con: Converter

    base: NDArray[int64] = field(
        default_factory=lambda: np.array([0], dtype=int64), init=False
    )
    state: NDArray[int64] = field(
        default_factory=lambda: np.array([0], dtype=int64), init=False
    )
    state_cache: NDArray[int64] = field(
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
    def __getitem__(self, item: tuple[T_1D, T_FP_MODE], /) -> NDArray[int64]: ...
    @overload
    def __getitem__(self, item: T_VA, /) -> PriceLike: ...

    def __getitem__(self, item: T_VP, /):
        if isinstance(item, tuple):
            if item[1] == "base":
                return self._fp.base[item[0], self.__idx]
            else:
                return self._fp.state[item[0], self.__idx]

        elif item == "poc":
            return self.__plike
        elif item == "vah":
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
        return int64(self._fp.base[self.__idy, key].sum())

    def __asks(self, key: slice | int64) -> int64:
        return int64(self._fp.base[self.__idy, key].sum())
