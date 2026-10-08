from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

import numba as nb
import numpy as np
from numba import types  # pyright: ignore[reportPrivateImportUsage]
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import float64, int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.footprint.engine.base import Base, JitStorage
from imprint._core.footprint.models.converter import to_idx, to_idy
from imprint._core.utils import FPArray, IndexGenerator

next_id = IndexGenerator()
BHM_VWAP_W: int = next_id()
BHM_VWAP_PW: int = next_id()
BHM_VWAP_P2W: int = next_id()
BHM_ConstantCount: int = next_id()


@dataclass(slots=True)
class Writer(Base, ABC):
    """Write market tick updates to high-performance trade footprint profiles and headers.

    Coordinates session management, grid initialization state, and delegated
    JIT-compiled update steps for incoming trade events.

    Attributes
    ----------
    counter_ticks : int
        Running total of successfully processed trades since session initialization.
    updater : JitFootprintUpdate
        Delegated JIT-compiled engine managing matrix and header updates.
    """

    counter_ticks: int = field(default=0, init=False)

    __meta_data: NDArray[float64] = field(init=False)
    updater: JitFootprintUpdate = field(init=False)

    @override
    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.__meta_data = np.zeros(shape=(2, BHM_ConstantCount), dtype=float64)
        self.updater = JitFootprintUpdate(
            meta_data=self.__meta_data, storage=self.storage
        )

    @override
    def reset(self) -> None:
        Base.reset(self)

        self.counter_ticks = 0

    @override
    def init_idx(self, nPrice: int64, timestamp: int64) -> None:
        """Reset internal metadata workspace upon index system re-initialization.

        Parameters
        ----------
        nPrice : int64
            Fixed-point reference price integer of the active session.
        timestamp : int64
            Reset epoch timestamp in milliseconds.
        """
        Base.init_idx(self, nPrice, timestamp)
        self.__meta_data.fill(0)

    @final
    def update_footprint(
        self, nPrice: int64, nQty: int64, timestamp: int64, is_sell: int64
    ) -> None:
        """Process an incoming trade tick and update the corresponding footprint profile.

        Parameters
        ----------
        nPrice : int64
            Fixed-point price integer of the incoming trade.
        nQty : int64
            Scaled fixed-point quantity integer of the incoming trade.
        timestamp : int64
            Trade execution timestamp in milliseconds.
        is_sell : int64
            Trade direction flag (``1`` for sell/bid side, ``0`` for buy/ask side).
        """
        if self.re_init & (c.RIF_session):
            self.init_session(nPrice, timestamp)

        if result := self.updater.update(
            nPrice, nQty, timestamp, is_sell, self.fp.base, self.fp.ctrade
        ):
            self.re_init: int = result
        else:
            self.counter_ticks += 1


spec = [  # pyright: ignore[reportUnknownVariableType]
    ("meta_data", types.Array(nb.float64, 2, "C")),
    ("storage", JitStorage.class_type.instance_type),  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitFootprintUpdate:
    """Execute JIT-compiled updates for footprint matrices, bar headers, and VWAP statistics.

    Parameters
    ----------
    meta_data : ndarray of shape (2, BHM_ConstantCount)
        Shared workspace holding tracking accumulators such as VWAP statistics.
    storage : JitStorage
        Underlying compiled state containing grid boundaries, bar headers,
        and dimension definitions.

    Attributes
    ----------
    meta_data : ndarray of shape (2, BHM_ConstantCount)
        Shared workspace holding tracking accumulators such as VWAP statistics.
    storage : JitStorage
        Underlying compiled state containing grid boundaries, bar headers,
        and dimension definitions.
    """

    def __init__(
        self, meta_data: NDArray[float64], storage: JitStorage
    ) -> None:
        self.meta_data: NDArray[float64] = meta_data
        self.storage: JitStorage = storage

    def update(
        self,
        nPrice: int64,
        nQty: int64,
        timestamp: int64,
        is_sell: int64,
        footprint: FPArray,
        ctrade: FPArray,
    ) -> int | None:
        """Update footprint volume matrix, bar headers, VWAP statistics, and bounding boxes.

        Parameters
        ----------
        nPrice : int64
            Fixed-point price integer of the incoming trade.
        nQty : int64
            Scaled fixed-point quantity integer of the incoming trade.
        timestamp : int64
            Trade execution timestamp in milliseconds.
        is_sell : int64
            Trade direction flag (``1`` for sell/bid side, ``0`` for buy/ask side).
        footprint : ndarray of shape (fp_rows, fp_cols)
            2D footprint array storing volume profiles per price level and bar column.
        ctrade : ndarray of shape (fp_rows, fp_cols)
            2D footprint array storing trade count profiles per price level and bar column.

        Returns
        -------
        int | None
            Bitmask integer containing re-initialization flags (``RIF_*``) if the trade falls
            outside grid boundaries, or ``None`` when the update succeeds.
        """
        _ = self.storage
        # - - -
        re_init: int = 0

        idx: int64 = to_idx(
            timestamp=timestamp,
            is_sell=is_sell,
            baseTimestamp=_.baseTimestamp,
            tims=_.tims,
            fp_cols=_.fp_cols,
        )
        if idx < 0:
            re_init |= c.RIF_session | c.RIF_idx
            return re_init

        _.idx[0] = int(idx)

        idy: int64 = to_idy(
            nPrice=nPrice,
            baseNprice=_.baseNprice,
            scale=_.scale,
            center=_.center,
            fp_rows=_.fp_rows,
        )
        if idy < 0:
            re_init |= c.RIF_session | c.RIF_idy
            return re_init

        # Update Footprint
        footprint[idy, idx] += nQty
        footprint[idy, _.idxVP[0]] += nQty
        footprint[idy, _.idxDP[0]] += -nQty if is_sell else nQty
        if _.with_ctrade[0]:
            ctrade[idy, idx] += 1
            ctrade[idy, _.idxVP[0]] += 1

        # Update Headers
        ho: int = _.headers_offset[0]
        bar: int64 = (idx & ~1) // 2
        bwo: int64 = ho + bar
        if _.headers[bwo, c.BH_CountTrade] == 0:
            _.headers[bwo, c.BH_Open : c.BH_Close + 1] = nPrice
            _.headers[bwo, c.BH_Time] = timestamp

            self._update_missing_bars(bar, ho)

        _.headers[bwo, c.BH_High] = max(nPrice, _.headers[bwo, c.BH_High])
        _.headers[bwo, c.BH_Low] = min(nPrice, _.headers[bwo, c.BH_Low])
        _.headers[bwo, c.BH_Close] = nPrice
        _.headers[bwo, c.BH_LastTradeTime] = timestamp

        _.headers[bwo, c.BH_CountTrade] += 1
        _.headers[bwo, c.BH_Volume] += nQty
        _.headers[bwo, c.BH_Delta] += -nQty if is_sell else nQty

        self._update_cvd(bar, bwo)
        self._update_vwap_and_bands(nPrice, nQty, bwo)

        _.idYmin[0] = min(_.idYmin[0], int(idy))
        _.idYmax[0] = (int(idy) + 1) if (_.idYmax[0] <= idy) else _.idYmax[0]

    def _update_missing_bars(self, bar: int64, ho: int) -> None:
        """Fill values for unpopulated bar gaps between active trades.

        Parameters
        ----------
        bar : int64
            Index of the active bar being updated.
        ho : int
            Offset parameter of the headers layout within the tracking array.
        """
        _ = self.storage
        # - - -
        prev_bar: int64 = bar - 1
        prev_t, prev_p = 0, 0

        while prev_bar >= 0:
            if _.headers[(ho + prev_bar), 0] == 0:
                prev_bar -= 1
            else:
                prev_t = _.headers[(ho + prev_bar), c.BH_Time]
                prev_p = _.headers[(ho + prev_bar), c.BH_Close]
                prev_bar += 1
                break

        while 0 <= prev_bar < bar:
            _.headers[(ho + prev_bar), c.BH_Time] = prev_t = prev_t + _.tims[0]
            _.headers[(ho + prev_bar), c.BH_Open : c.BH_Close + 1] = prev_p
            prev_bar += 1

    def _update_cvd(self, bar: int64, bwo: int64) -> None:
        """Calculate Cumulative Volume Delta (CVD) for the current bar.

        Parameters
        ----------
        bar : int64
            Index of the active bar being updated.
        bwo : int64
            Calculated target row index within the headers tracking array.
        """
        _ = self.storage
        # - - -
        if bar > 0:
            _.headers[bwo, c.BH_CVD] = (
                _.headers[bwo, c.BH_Delta] + _.headers[bwo - 1, c.BH_CVD]
            )
        else:
            _.headers[bwo, c.BH_CVD] = _.headers[bwo, c.BH_Delta]

    def _update_vwap_and_bands(
        self, nPrice: int64, nQty: int64, bwo: int64
    ) -> None:
        """Update Volume Weighted Average Price (VWAP) and rolling standard deviation bands.

        Parameters
        ----------
        nPrice : int64
            Fixed-point price integer of the incoming trade.
        nQty : int64
            Scaled fixed-point quantity integer of the incoming trade.
        bwo : int64
            Calculated target row index within the headers tracking array.
        """
        _ = self.storage
        # - - -
        price = round(nPrice / _.price_mult[0], _.price_prec[0])
        qty = round(nQty / _.qty_mult[0], _.qty_prec[0])
        self.meta_data[0, BHM_VWAP_W] += qty
        self.meta_data[0, BHM_VWAP_PW] += price * qty
        self.meta_data[0, BHM_VWAP_P2W] += (price**2) * qty
        w, pw, p2w = self.meta_data[0, :]
        vwap: float64 = pw / w
        variance = max(0.0, ((p2w / w) - (vwap**2)))
        vwsd = np.sqrt(variance)
        upper_band, lower_band = vwap + (2.0 * vwsd), vwap - (2.0 * vwsd)
        _.headers[bwo, c.BH_VWAP] = round(vwap * _.price_mult[0])
        _.headers[bwo, c.BH_VWAP_LOWER_BAND] = round(
            lower_band * _.price_mult[0]
        )
        _.headers[bwo, c.BH_VWAP_UPPER_BAND] = round(
            upper_band * _.price_mult[0]
        )
