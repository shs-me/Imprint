from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast, final, overload, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from .converter import Converter

if TYPE_CHECKING:
    from .typing import T_FP, T_INDEX, T_SLICE, T_VP


@final
class FPArray(np.ndarray):
    def __new__(cls, rows: int | int64, cols: int | int64) -> FPArray:
        obj = super().__new__(cls, shape=(rows, cols), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return

    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_INDEX], /) -> int64: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: T_FP, /) -> FPArray: ...
    @override
    def __getitem__(self, key: T_FP, /):  # pyright: ignore[reportInconsistentOverload,reportIncompatibleMethodOverride]
        return super().__getitem__(key)

    def pading(self, before: int, after: int) -> FPArray:
        return np.pad(self, pad_width=((before, after), (0, 0))).view(FPArray)


@dataclass(slots=True)
class Chart(ABC):
    con: Converter

    base: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    state: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)

    state_cache: NDArray[int64] = field(init=False)
    headers: NDArray[int64] = field(init=False)
    headers_offset: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    def __post_init__(self) -> None:
        self.state_cache = np.zeros((c.CSD_ConstantCount,), dtype=int64)
        self.headers = np.zeros(
            shape=(self.con.chart_range * self.con.bar_count, c.BH_ConstantCount),
            dtype=int64,
        )


@dataclass(slots=True)
class ProfileLike[T](ABC):
    _idx: int

    _arr: FPArray = field(init=False)

    @overload
    def __getitem__(self, key: T_INDEX, /) -> int64: ...
    @overload
    def __getitem__(self, key: T_SLICE, /) -> FPArray: ...
    def __getitem__(self, key: T_VP, /):  # pyright: ignore[reportInconsistentOverload]
        return self._arr[key, self._idx]


@final
@dataclass(slots=True)
class PriceLike[T]:
    _con: Converter
    _qlike: QtyLike[T]

    n: int64 = field(default=int64(0), init=False)

    def __getitem__(self, nPrice: int64) -> PriceLike[T]:
        self.n = nPrice
        return self

    @property
    def id(self) -> int64:
        return cast(int64, self._con.to_idy(self.n))

    @property
    def qty(self) -> QtyLike[T]:
        return self._qlike[self.id]


@dataclass(slots=True)
class QtyLike[T](ABC):
    _idy: int64 = field(default=int64(0), init=False)

    @abstractmethod
    def __getitem__(self, idy: int64) -> QtyLike[T]: ...
