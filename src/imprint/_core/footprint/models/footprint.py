from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast, final, override

import numpy as np
from numpy import int64

from imprint._core import constant as c
from imprint._core.footprint.models.bar import Bar
from imprint._core.footprint.models.base import Chart, PriceLike, QtyLike
from imprint._core.footprint.models.converter import Converter
from imprint._core.utils import FPArray
from imprint._core.utils.base import DPArray, VPArray


@final
@dataclass(slots=True)
class Footprint(Chart):
    """Represents a complete order flow footprint chart containing bars, profiles, and trade data.

    Parameters
    ----------
    con : Converter
        Converter instance handling coordinate mapping between price levels and indices.
    last_idx : memoryview
        Memory view buffer storing the index of the latest active bar.

    Attributes
    ----------
    headers_offset : memoryview
        Memory view buffer for tracking bar offset indices.
    vp : VolumeProfile[Footprint]
        Chart-level volume profile analytics interface.
    dp : DeltaProfile[Footprint]
        Chart-level delta profile analytics interface.
    last_bar : int, read-only
        Index of the most recent active bar.
    vwap : PriceLike[Footprint], read-only
        Volume-Weighted Average Price of the last bar.
    vwap_up_band : PriceLike[Footprint], read-only
        Upper VWAP band price of the last bar.
    vwap_low_band : PriceLike[Footprint], read-only
        Lower VWAP band price of the last bar.
    """

    con: Converter
    last_idx: memoryview

    headers_offset: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    vp: VolumeProfile[Footprint] = field(init=False)
    dp: DeltaProfile[Footprint] = field(init=False)

    __bars: list[Bar] = field(init=False)
    __plike: PriceLike[Footprint] = field(init=False)

    def __post_init__(self) -> None:
        self.vp = VolumeProfile(self)
        self.dp = DeltaProfile(self)
        self.__plike = PriceLike(self.con, Qty(self))

    def post_init(self) -> None:
        self.headers = np.zeros(
            shape=(self.con.total_bar_count, c.BH_ConstantCount), dtype=int64
        )
        self.__bars = [
            Bar(self, idXbid) for idXbid in range(0, self.con.fp_cols, 2)
        ]

    def __getitem__(self, idx: int | int64) -> Bar:
        """Select a bar by its index

        Parameters
        ----------
        idx : int | int64
            Bar index identifier.

        Returns
        -------
        Bar
            The configured bar instance.
        """
        return self.__bars[(idx & ~1) // 2]

    def _re_init_arr(  # pyright: ignore[reportUnusedFunction]
        self, base: FPArray, state: FPArray | None, ctrade: FPArray | None
    ) -> None:
        """Reinitialize chart array buffers and propagate updates to volume and delta profiles.

        Parameters
        ----------
        base : FPArray
            New base footprint array buffer.
        state : FPArray | None
            New state array buffer, or None to retain existing state.
        ctrade : FPArray | None
            New cumulative trade array buffer, or None to retain existing ctrade.
        """
        self.base = base
        if state is not None:
            self.state = state
        if ctrade is not None:
            self.ctrade = ctrade

        self.vp._re_init_arr()
        self.dp._re_init_arr()

    @property
    def last_bar(self) -> int:
        return (self.last_idx[0] & ~1) // 2

    @property
    def vwap(self) -> PriceLike[Footprint]:
        return self.__plike[self.headers[self.last_bar, c.BH_VWAP]]

    @property
    def vwap_up_band(self) -> PriceLike[Footprint]:
        return self.__plike[self.headers[self.last_bar, c.BH_VWAP_UPPER_BAND]]

    @property
    def vwap_low_band(self) -> PriceLike[Footprint]:
        return self.__plike[self.headers[self.last_bar, c.BH_VWAP_LOWER_BAND]]


@dataclass(slots=True)
class VolumeProfile[T]:
    """Manages volume profile analytics across price levels for a footprint chart.

    Parameters
    ----------
    _fp : Footprint
        Parent footprint chart instance.

    Attributes
    ----------
    base : VPArray
        Volume profile base view extracted from footprint data.
    state : VPArray
        Volume profile state view extracted from footprint data.
    poc : PriceLike[T], read-only
        Point of Control (POC) price level with the highest volume in the last bar.
    vah : PriceLike[T], read-only
        Value Area High (VAH) price level for the last bar.
    val : PriceLike[T], read-only
        Value Area Low (VAL) price level for the last bar.
    """

    _fp: Footprint

    _plike: PriceLike[T] = field(init=False)
    base: VPArray = field(init=False)
    state: VPArray = field(init=False)

    def __post_init__(self) -> None:
        self._plike = PriceLike(self._fp.con, Qty(self._fp))

    def _re_init_arr(self) -> None:
        """Rebind volume profile array views to updated parent footprint arrays."""
        self.base = cast(VPArray, self._fp.base[:, self._fp.con.idxVP])
        self.state = cast(VPArray, self._fp.state[:, self._fp.con.idxVP])

    @property
    def poc(self) -> PriceLike[T]:
        return self._plike[self._fp.headers[self._fp.last_bar, c.BH_POC_FP]]

    @property
    def vah(self) -> PriceLike[T]:
        return self._plike[self._fp.headers[self._fp.last_bar, c.BH_VAH_FP]]

    @property
    def val(self) -> PriceLike[T]:
        return self._plike[self._fp.headers[self._fp.last_bar, c.BH_VAL_FP]]


@dataclass(slots=True)
class DeltaProfile[T]:
    """Manages delta profile analytics across price levels for a footprint chart.

    Parameters
    ----------
    _fp : Footprint
        Parent footprint chart instance.

    Attributes
    ----------
    base : DPArray
        Delta profile base view extracted from footprint data.
    state : DPArray
        Delta profile state view extracted from footprint data.
    """

    _fp: Footprint

    base: DPArray = field(init=False)
    state: DPArray = field(init=False)

    def _re_init_arr(self) -> None:
        """Rebind delta profile array views to updated parent footprint arrays."""
        self.base = cast(DPArray, self._fp.base[:, self._fp.con.idxDP])
        self.state = cast(DPArray, self._fp.state[:, self._fp.con.idxDP])


@final
@dataclass(slots=True)
class Qty[T](QtyLike[T]):
    """Provides volume, delta, bid, and ask quantities at specific price level indices for a footprint.

    Parameters
    ----------
    _fp : Footprint
        Parent footprint chart instance.

    Attributes
    ----------
    delta : int64, read-only
        Net delta (ask volume minus bid volume or profile delta) at the configured price index.
    sum : int64, read-only
        Total volume (sum of bid and ask) at the configured price index.
    bid : int64, read-only
        Estimated or derived bid volume at the configured price index.
    ask : int64, read-only
        Estimated or derived ask volume at the configured price index.
    """

    _fp: Footprint

    @override
    def __getitem__(self, idy: int64) -> Qty[T]:
        """Configure the target price level index for quantity queries.

        Parameters
        ----------
        idy : int64
            Price level index coordinate.

        Returns
        -------
        Qty[T]
            The current instance configured with the specified index.
        """
        self._idy = idy
        return self

    @property
    def delta(self) -> int64:
        return self._fp.dp.base[self._idy]

    @property
    def sum(self) -> int64:
        return self._fp.vp.base[self._idy]

    @property
    def bid(self) -> int64:
        return (self.sum + self.delta) // 2

    @property
    def ask(self) -> int64:
        return (self.sum - self.delta) // 2
