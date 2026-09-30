from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self, final, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray


@final
@dataclass(slots=True)
class IndexGenerator:
    val: int = field(default=0, init=False)

    def __call__(self) -> int:
        v = self.val
        self.val += 1
        return v


class FPArray(np.ndarray):
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


class RowArray(FPArray): ...


class ColArray(FPArray): ...


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
    def __new__(cls, count_vars: int | int64) -> VarArray:
        obj = super().__new__(cls, shape=(count_vars,), dtype=int64)
        obj.fill(0)
        return obj

    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None:
        if obj is None:
            return
