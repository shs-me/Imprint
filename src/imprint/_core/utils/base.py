"""Fixed-point numerical array wrappers, sequence generators, and specialized trading data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self, final

import numpy as np
from numpy import int64

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


class T1DArray(np.ndarray): ...


class RowArray(T1DArray): ...


class ColArray(T1DArray): ...


class T2DArray(T1DArray): ...


@final
class TradesArray(T2DArray):
    """2D fixed-point array specialized for trade records with optional power-of-two row capacity allocation."""

    def __new__(cls, rows: int, pow: bool = False) -> Self:
        obj = super().__new__(
            cls,
            shape=((1 << (rows).bit_length()) if pow else rows, 4),
            dtype=int64,
        )
        obj.fill(0)
        return obj


@final
class OrdersHistoryArray(T2DArray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.TP_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    def padding(self, after: int) -> OrdersHistoryArray:
        return np.pad(self, pad_width=((0, after), (0, 0))).view(
            OrdersHistoryArray
        )


@final
class EquityHistoryArray(T2DArray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.EH_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj


@final
class OrderBookArray(T2DArray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.OB_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj


@final
class ExecutedOrdersArray(T2DArray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows * 2, c.TP_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj
