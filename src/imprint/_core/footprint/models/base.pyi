from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Self, final, overload, override

from numpy import int64
from numpy.typing import NDArray

from imprint._core.footprint.models.converter import Converter
from imprint._core.typing import (
    T_ASK,
    T_BAR,
    T_BID,
    T_DP,
    T_FP,
    T_IDY,
    T_INDEX,
    T_MASK,
    T_PROFILE,
    T_SLICE,
    T_VP,
)
from imprint._core.utils.base import ColArray, RowArray, T2DArray

@dataclass(slots=True)
class Chart(ABC):
    con: Converter = ...
    base: BarsArray = ...
    profile: ProfileArray = ...
    headers: BarsHeadersArray = ...
    headers_offset: memoryview = ...
    last_bar: memoryview = ...

class BarsArray(T2DArray):
    def __new__(
        cls, count: int, height: int, with_state: int = 0, with_ctrade: int = 0
    ) -> Self: ...
    @overload
    def __getitem__(
        self, key: tuple[T_INDEX, T_INDEX, T_INDEX], /
    ) -> int64: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: T_BAR, /) -> BarArray: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: tuple[T_BAR, T_IDY, T_SLICE], /) -> BarArray: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: T_FP, /) -> Self: ...
    @override
    def __getitem__(self, key: T_FP, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
    def __setitem__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        key: T_BAR
        | tuple[T_BAR, T_IDY, T_BID | T_ASK | T_SLICE | T_INDEX]
        | T_MASK,
        value: int | int64 | NDArray[int64] | Sequence[int | int64],
        /,
    ) -> None: ...

class BarArray(BarsArray):
    @overload
    def __getitem__(self, key: T_SLICE, /) -> Self: ...
    @overload
    def __getitem__(self, key: T_INDEX, /) -> RowArray: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_SLICE], /) -> RowArray: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_ASK], /) -> AskArray: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_BID], /) -> BidArray: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_INDEX], /) -> ColArray: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_INDEX], /) -> int64: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_SLICE], /) -> Self: ...
    @overload
    def __getitem__(self, key: T_MASK, /) -> NDArray[Any]: ...
    @override
    def __getitem__(self, key: T_FP, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]

@final
class BidArray(ColArray): ...

@final
class AskArray(ColArray): ...

class ProfileArray(T2DArray):
    def __new__(cls, rows: int) -> Self: ...
    @overload
    def __getitem__(self, key: T_DP | tuple[T_DP, T_SLICE], /) -> DPArray: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: T_VP | tuple[T_VP, T_SLICE], /) -> VPArray: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_INDEX], /) -> int64: ...
    @overload
    def __getitem__(self, key: T_MASK, /) -> NDArray[Any]: ...
    @overload
    def __getitem__(self, key: T_PROFILE, /) -> Self: ...
    @override
    def __getitem__(self, key: T_PROFILE, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
    def padding(self, before: int, after: int) -> Self: ...

@final
class VPArray(ColArray): ...

@final
class DPArray(ColArray): ...

@final
class BarsHeadersArray(T2DArray):
    def __new__(cls, rows: int) -> Self: ...
    def padding(self, after: int) -> Self: ...
