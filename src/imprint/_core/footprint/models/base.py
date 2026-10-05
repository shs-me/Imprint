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
    """Abstract base class representing a financial chart data structure.

    Attributes
    ----------
    con : Converter
        Converter instance handling coordinate mapping between price levels and indices.
    base : FPArray
        Underlying multi-dimensional array storing base footprint data.
    state : FPArray
        Underlying multi-dimensional array storing state flags and metadata.
    ctrade : FPArray
        Underlying multi-dimensional array storing cumulative trade information.
    headers : ndarray of shape (total_bar_count, BH_ConstantCount)
        Two-dimensional integer array storing bar header metrics and metadata.
    headers_offset : memoryview
        Memory view buffer for tracking bar offset indices.
    """

    con: Converter

    base: FPArray = field(init=False)
    state: FPArray = field(init=False)
    ctrade: FPArray = field(init=False)

    headers: NDArray[int64] = field(init=False)
    headers_offset: memoryview = field(init=False)


@final
@dataclass(slots=True)
class PriceLike[T]:
    """Wraps price level identifiers to provide chained access to associated quantity metrics.

    Parameters
    ----------
    _con : Converter
        Converter instance for price-to-index mapping.
    _qlike : QtyLike[T]
        Quantity collection container providing lookup by price level index.

    Attributes
    ----------
    n : int64
        Raw price level integer value.
    id : int64, read-only
        Converted index corresponding to the current price level.
    qty : QtyLike[T], read-only
        Quantity wrapper configured for the current price level index.
    """

    _con: Converter
    _qlike: QtyLike[T]

    n: int64 = field(default=int64(0), init=False)

    def __getitem__(self, nPrice: int64) -> PriceLike[T]:
        """Configure the target price level integer.

        Parameters
        ----------
        nPrice : int64
            Raw price level value to set.

        Returns
        -------
        PriceLike[T]
            The current instance updated with the specified price level.
        """
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
    """Abstract base class for quantity metrics indexed by price level coordinate.

    Attributes
    ----------
    _idy : int64
        Internal price level index coordinate.
    """

    _idy: int64 = field(default=int64(0), init=False)

    @abstractmethod
    def __getitem__(self, idy: int64) -> QtyLike[T]:
        """Select quantity metrics for a given price level index.

        Parameters
        ----------
        idy : int64
            Price level index coordinate.

        Returns
        -------
        QtyLike[T]
            The configured quantity instance.
        """
        ...
