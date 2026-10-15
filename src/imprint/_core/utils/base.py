"""Fixed-point numerical array wrappers, sequence generators, and specialized trading data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self, final, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

import imprint._core.constant as c


@final
@dataclass(slots=True)
class IndexGenerator:
    """Generate monotonically increasing integer indices starting from zero."""

    val: int = field(default=0, init=False)

    def __call__(self) -> int:
        """Increment and return the next sequential integer index."""
        v = self.val
        self.val += 1
        return v


class FPArray(np.ndarray):
    """Fixed-point 2D NumPy ndarray base class for scaled integer arithmetic."""

    def __new__(cls, rows: int | int64, cols: int | int64) -> Self:
        obj = super().__new__(cls, shape=(rows, cols), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return

    def padding(self, before: int, after: int) -> FPArray:
        return np.pad(self, pad_width=((before, after), (0, 0))).view(FPArray)


class RowArray(FPArray):
    """Row-oriented slice view of a fixed-point array."""


class ColArray(FPArray):
    """Column-oriented slice view of a fixed-point array."""


@final
class BidArray(ColArray):
    """Specialized column array representing aggregated bid order levels."""


@final
class AskArray(ColArray):
    """Specialized column array representing aggregated ask order levels."""


@final
class VPArray(ColArray):
    """Specialized column array representing volume profile statistics."""


@final
class DPArray(ColArray):
    """Specialized column array representing depth profile statistics."""


@final
class TradesArray(np.ndarray):
    """2D fixed-point array specialized for trade records with power-of-two row capacity allocation."""

    def __new__(cls, rows: int, cols: int) -> Self:
        power_two = 1 << (rows).bit_length()
        obj = super().__new__(cls, shape=(power_two, cols), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return


@final
class FPHeadersArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.BH_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return


@final
class OrdersHistoryArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.TP_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return

    def padding(self, after: int) -> OrdersHistoryArray:
        return np.pad(self, pad_width=((0, after), (0, 0))).view(
            OrdersHistoryArray
        )


@final
class EquityHistoryArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.EH_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return


@final
class OrderBookArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.OB_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return


@final
class ExecutedOrdersArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows * 2, c.TP_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return
