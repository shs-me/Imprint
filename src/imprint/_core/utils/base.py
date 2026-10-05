"""Fixed-point numerical array wrappers, sequence generators, and specialized trading data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self, final, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray


@final
@dataclass(slots=True)
class IndexGenerator:
    """Generate monotonically increasing integer indices starting from zero.

    Attributes
    ----------
    val : int
        Current internal counter value.
    """

    val: int = field(default=0, init=False)

    def __call__(self) -> int:
        """Increment and return the next sequential integer index.

        Returns
        -------
        int
            The current index value before incrementing.
        """
        v = self.val
        self.val += 1
        return v


class FPArray(np.ndarray):
    """Fixed-point 2D NumPy ndarray base class for scaled integer arithmetic.

    Parameters
    ----------
    rows : int | int64
        Number of rows in the 2D array. Must be non-negative.
    cols : int | int64
        Number of columns in the 2D array. Must be non-negative.
    """

    def __new__(cls, rows: int | int64, cols: int | int64) -> Self:
        """Allocate and initialize a zero-filled int64 fixed-point array."""
        obj = super().__new__(cls, shape=(rows, cols), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        """Finalize array state during view casting and slicing operations."""
        if obj is None:
            return

    def padding(self, before: int, after: int) -> FPArray:
        """Pad rows before and after with zeros along the first axis.

        Parameters
        ----------
        before : int
            Number of zero rows to prepend. Must be non-negative.
        after : int
            Number of zero rows to append. Must be non-negative.

        Returns
        -------
        FPArray
            A new padded fixed-point array view.
        """
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
class VarArray(np.ndarray):
    """1D fixed-point array specialized for variable or parameter storage.

    Parameters
    ----------
    count_vars : int | int64
        Number of variables/elements. Must be non-negative.
    """

    def __new__(cls, count_vars: int | int64) -> VarArray:
        """Allocate and initialize a zero-filled 1D int64 variable array."""
        obj = super().__new__(cls, shape=(count_vars,), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        """Finalize array state during view casting and slicing operations."""
        if obj is None:
            return


@final
class TradesArray(np.ndarray):
    """2D fixed-point array specialized for trade records with power-of-two row capacity allocation.

    Parameters
    ----------
    rows : int
        Initial row capacity requirement. Rounded up to the next power of two.
    cols : int
        Number of attribute columns per trade record.
    """

    def __new__(cls, rows: int, cols: int) -> TradesArray:
        """Allocate and initialize a zero-filled int64 trades array sized to the nearest power of two."""
        power_two = 1 << (rows).bit_length()
        obj = super().__new__(cls, shape=(power_two, cols), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        """Finalize array state during view casting and slicing operations."""
        if obj is None:
            return
