from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self, final, overload, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint._core.typing import (
    T_1D,
    T_ASK,
    T_BID,
    T_FP,
    T_IDX,
    T_IDY,
    T_INDEX,
    T_SLICE,
)

@final
@dataclass(slots=True)
class IndexGenerator:
    def __call__(self) -> int: ...

class FPArray(np.ndarray):
    def __new__(cls, rows: int | int64, cols: int | int64) -> Self: ...
    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None: ...
    @override
    def __iter__(self) -> Iterator[RowArray]: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    @overload
    def __getitem__(self, key: T_SLICE, /) -> FPArray: ...
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
    def __getitem__(self, key: tuple[T_SLICE, T_SLICE], /) -> FPArray: ...
    @override
    def __getitem__(self, key: T_FP, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
    def padding(self, before: int, after: int) -> FPArray: ...

class T1DArray(FPArray):
    @override
    def __iter__(self) -> Iterator[int64]: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    @overload
    def __getitem__(self, key: T_INDEX, /) -> int64: ...
    @overload
    def __getitem__(self, key: T_SLICE, /) -> Self: ...
    @override
    def __getitem__(self, key: T_1D, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]

class RowArray(T1DArray): ...
class ColArray(T1DArray): ...

@final
class BidArray(ColArray): ...

@final
class AskArray(ColArray): ...

@final
class VPArray(ColArray): ...

@final
class DPArray(ColArray): ...

@final
class VarArray(np.ndarray):
    def __new__(cls, count_vars: int | int64) -> VarArray: ...
    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None: ...
    @override
    def __setitem__(self, key: int, var: int | int64) -> None: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    @overload
    def __getitem__(self, key: T_INDEX, /) -> int64: ...
    @overload
    def __getitem__(self, key: T_SLICE, /) -> VarArray: ...
    @override
    def __getitem__(self, key: T_1D, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]

@final
class TradesArray(np.ndarray):
    def __new__(cls, rows: int, cols: int) -> TradesArray: ...
    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None: ...
    @override
    def __iter__(self) -> Iterator[RowArray]: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    @overload
    def __getitem__(self, key: T_SLICE, /) -> TradesArray: ...
    @overload
    def __getitem__(self, key: T_INDEX, /) -> RowArray: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_SLICE], /) -> RowArray: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_INDEX], /) -> ColArray: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_INDEX], /) -> int64: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_SLICE], /) -> TradesArray: ...
    @override
    def __getitem__(self, key: T_IDY | tuple[T_IDY, T_IDX], /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
