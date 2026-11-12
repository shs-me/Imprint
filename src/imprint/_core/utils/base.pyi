from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Self, final, overload, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint._core.typing import T_1D, T_IDX, T_IDY, T_INDEX, T_MASK, T_SLICE

@final
@dataclass(slots=True)
class IndexGenerator:
    def __call__(self) -> int: ...

class T1DArray(np.ndarray):
    @override
    def __iter__(self) -> Iterator[int64]: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    @overload
    def __getitem__(self, key: T_INDEX, /) -> int64: ...
    @overload
    def __getitem__(self, key: T_SLICE, /) -> Self: ...
    @overload
    def __getitem__(self, key: T_MASK, /) -> NDArray[Any]: ...
    @override
    def __getitem__(self, key: T_1D | T_MASK, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
    @override
    def __setitem__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        key: T_1D | T_MASK,
        value: int | int64 | NDArray[int64] | Sequence[int | int64],
        /,
    ) -> None: ...

class RowArray(T1DArray): ...
class ColArray(T1DArray): ...

class T2DArray(T1DArray):
    @override
    def __iter__(self) -> Iterator[RowArray]: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    @overload
    def __getitem__(self, key: T_SLICE, /) -> Self: ...
    @overload
    def __getitem__(self, key: T_INDEX, /) -> RowArray: ...
    @overload
    def __getitem__(self, key: T_MASK, /) -> NDArray[Any]: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_SLICE], /) -> RowArray: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_INDEX], /) -> ColArray: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_INDEX], /) -> int64: ...
    @overload
    def __getitem__(self, key: tuple[T_SLICE, T_SLICE], /) -> Self: ...
    @override
    def __getitem__(self, key: T_IDY | tuple[T_IDY, T_IDX] | T_MASK, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
    @override
    def __setitem__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        key: T_IDY | tuple[T_IDY, T_IDX] | T_MASK,
        value: int | int64 | NDArray[int64] | Sequence[int | int64],
        /,
    ) -> None: ...

@final
class TradesArray(T2DArray):
    def __new__(cls, rows: int, pow: bool = False) -> Self: ...

@final
class OrdersHistoryArray(T2DArray):
    def __new__(cls, rows: int) -> Self: ...
    def padding(self, after: int) -> Self: ...

@final
class EquityHistoryArray(T2DArray):
    def __new__(cls, rows: int) -> Self: ...

@final
class OrderBookArray(T2DArray):
    def __new__(cls, rows: int) -> Self: ...

@final
class ExecutedOrdersArray(T2DArray):
    def __new__(cls, rows: int) -> Self: ...
