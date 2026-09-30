from dataclasses import dataclass
from typing import Any, final, overload, override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint._core.typing import T_1D, T_FP, T_INDEX, T_SLICE

@final
@dataclass(slots=True)
class IndexGenerator:
    def __call__(self) -> int: ...

@final
class FPArray(np.ndarray):
    def __new__(cls, rows: int | int64, cols: int | int64) -> FPArray: ...
    @override
    def __array_finalize__(self, obj: NDArray[Any] | None, /) -> None: ...
    @overload
    def __getitem__(self, key: tuple[T_INDEX, T_INDEX], /) -> int64: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __getitem__(self, key: T_FP, /) -> FPArray: ...
    @override
    def __getitem__(self, key: T_FP, /): ...  # pyright: ignore[reportIncompatibleMethodOverride,reportUnknownParameterType]
    def padding(self, before: int, after: int) -> FPArray: ...

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
