from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import cast, final

from numpy import int64
from numpy.typing import NDArray

from imprint._core.footprint.models.converter import Converter
from imprint._core.utils import FPArray


@dataclass(slots=True)
class Chart(ABC):
    con: Converter

    base: FPArray = field(init=False)
    state: FPArray = field(init=False)
    ctrade: FPArray = field(init=False)

    headers: NDArray[int64] = field(init=False)
    headers_offset: memoryview = field(init=False)


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
