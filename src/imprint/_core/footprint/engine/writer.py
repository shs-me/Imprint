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

import imprint._core.constant as c
from imprint._core.footprint.engine.base import Base, JitStorage
from imprint._core.footprint.models.converter import to_idy
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils import IndexGenerator

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

    save_trade_time: bool = field(default=False, init=False)
    trade_time: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
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
        _ = self.fp
        # - - -
        new_bar: int = _.last_bar[0] + 1
        if new_bar >= _.con.bar_count[0]:
            _.last_bar[0] = 0
            _.headers_offset[0] += _.con.bar_count[0]
        else:
            _.last_bar[0] = new_bar

        self.counter_ticks = 0

    @final
    def update_footprint(
        self, nPrice: int64, nQty: int64, timestamp: int64, is_sell: int64
    ) -> None:
        if (
            result := self.updater.update(nPrice, nQty, timestamp, is_sell)
        ) is None:
            self.counter_ticks += 1
            if self.save_trade_time and not self.trade_time[0]:
                self.trade_time[0] = int(timestamp)
        else:
            if result == 1:
                return self.manager.set_proc_sc(
                    scs.PRICE_OUT_OF_BAR_BOUNDS, wait_main_task=True
                )
            elif result == 0:
                self.fp.headers = self.storage.headers = (
                    self.fp.headers.padding(10_000)
                )
            elif result == 2:
                self.fp.profile = self.storage.profile = (
                    self.fp.profile.padding(5000, 5000)
                )

            self.update_footprint(nPrice, nQty, timestamp, is_sell)


spec = [  # pyright: ignore[reportUnknownVariableType]
    ("meta_data", types.Array(nb.float64, 2, "C")),
    ("storage", JitStorage.class_type.instance_type),  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitFootprintUpdate:
    """Execute JIT-compiled updates for footprint matrices, bar headers, and VWAP statistics."""

    def __init__(
        self, meta_data: NDArray[float64], storage: JitStorage
    ) -> None:
        self.meta_data: NDArray[float64] = meta_data
        self.storage: JitStorage = storage

    def update(
        self, nPrice: int64, nQty: int64, timestamp: int64, is_sell: int64
    ) -> int | None:
        """Update footprint volume matrix, bar headers, VWAP statistics, and bounding boxes."""
        _ = self.storage
        # - - -
        ho: int = _.headers_offset[0]
        bt: int = _.bar_type[0]
        btt: int = _.bar_close_trigger[0]
        bar: int = _.last_bar[0]
        bwo: int = ho + bar

        if bwo >= _.headers.shape[0]:
            return 0
        if (
            bt & c.BT_Time and (timestamp - _.headers[bwo, c.BH_OpenTime]) > btt
        ) or (bt & c.BT_Tick and (_.headers[bwo, c.BH_CountTrade] + 1) > btt):
            _.closed_bar[0] = bar
            new_bar: int = bar + 1
            if new_bar >= _.bar_count[0]:
                _.last_bar[0] = 0
                _.headers_offset[0] += _.bar_count[0]
            else:
                _.last_bar[0] = new_bar

            bar = _.last_bar[0]
            bwo = ho + bar

        if not _.headers[bwo, c.BH_BaseNprice]:
            _.headers[bwo, c.BH_BaseNprice] = int(
                (nPrice // _.scale[0]) * _.scale[0]
            )

        idy: int64 = to_idy(
            nPrice=nPrice,
            baseNprice=_.headers[bwo, c.BH_BaseNprice],
            bar_height=_.bar_height,
            scale=_.scale,
            center=_.center,
        )
        if idy < 0:
            return 1

        if 0 <= idy < _.profile.shape[1]:
            _.profile[0, idy] += nQty
            _.profile[1, idy] += -nQty if is_sell else nQty
        else:
            return 2

        _.last_side[0] = side = 0 if is_sell else 1

        if _.headers[bwo, c.BH_CountTrade] == 0:
            _.fp[bar] = 0
            _.headers[bwo, c.BH_Open : c.BH_Close + 1] = nPrice
            if bt & c.BT_Time:
                _.headers[bwo, c.BH_OpenTime] = int(
                    timestamp - (timestamp % _.bar_close_trigger[0])
                )
                self._update_missing_bars(bar, ho)
            else:
                _.headers[bwo, c.BH_OpenTime] = timestamp

        _.fp[bar, idy, side] += nQty
        if _.with_ctrade[0]:
            _.fp[bar, idy, (4 if _.with_state[0] else 2) + side] += 1

        _.headers[bwo, c.BH_High] = max(nPrice, _.headers[bwo, c.BH_High])
        _.headers[bwo, c.BH_Low] = min(nPrice, _.headers[bwo, c.BH_Low])
        _.headers[bwo, c.BH_Close] = nPrice
        _.headers[bwo, c.BH_CloseTime] = timestamp

        _.headers[bwo, c.BH_CountTrade] += 1
        _.headers[bwo, c.BH_Volume] += nQty
        _.headers[bwo, c.BH_Delta] += -nQty if is_sell else nQty

        self._update_cvd(bwo)
        self._update_vwap_and_bands(nPrice, nQty, bwo)

        _.idYmin[0] = min(_.idYmin[0], int(idy))
        _.idYmax[0] = (int(idy) + 1) if (_.idYmax[0] <= idy) else _.idYmax[0]

    def _update_missing_bars(self, bar: int, ho: int) -> None:
        """Fill values for unpopulated bar gaps between active trades."""
        _ = self.storage
        # - - -
        zero: int64 = int64(0)
        prev_bar: int = bar - 1
        prev_p: int64 = zero
        prev_time: int64 = zero
        prev_cvd: int64 = zero
        prev_vwap: int64 = zero
        prev_vwap_l: int64 = zero
        prev_vwap_u: int64 = zero
        prev_atr: int64 = zero
        found_prev: bool = False

        while prev_bar >= 0:
            b_idx = ho + prev_bar
            if (
                _.headers[b_idx, c.BH_CountTrade] > 0
                or _.headers[b_idx, c.BH_Open] > 0
            ):
                prev_p = _.headers[b_idx, c.BH_Close]
                prev_time = _.headers[b_idx, c.BH_OpenTime]
                prev_cvd = _.headers[b_idx, c.BH_CVD]
                prev_vwap = _.headers[b_idx, c.BH_VWAP]
                prev_vwap_l = _.headers[b_idx, c.BH_VWAP_LOWER_BAND]
                prev_vwap_u = _.headers[b_idx, c.BH_VWAP_UPPER_BAND]
                prev_atr = _.headers[b_idx, c.BH_ATR]
                found_prev = True
                prev_bar += 1
                break

            prev_bar -= 1

        if not found_prev:
            prev_bar = 0
            prev_p = _.headers[ho + bar, c.BH_Open]

        while prev_bar < bar:
            cur_bwo: int = ho + prev_bar
            _.headers[cur_bwo, c.BH_OpenTime] = prev_time + (
                prev_bar * _.bar_close_trigger[0]
            )
            _.headers[cur_bwo, c.BH_CloseTime] = _.headers[
                cur_bwo, c.BH_OpenTime
            ]

            _.headers[cur_bwo, c.BH_Open : c.BH_Close + 1] = prev_p

            _.headers[cur_bwo, c.BH_CVD] = prev_cvd
            _.headers[cur_bwo, c.BH_VWAP] = prev_vwap
            _.headers[cur_bwo, c.BH_VWAP_LOWER_BAND] = prev_vwap_l
            _.headers[cur_bwo, c.BH_VWAP_UPPER_BAND] = prev_vwap_u
            _.headers[cur_bwo, c.BH_ATR] = prev_atr

            prev_bar += 1

    def _update_cvd(self, bwo: int) -> None:
        """Calculate Cumulative Volume Delta (CVD) for the current bar."""
        _ = self.storage
        # - - -
        if bwo > 0:
            _.headers[bwo, c.BH_CVD] = (
                _.headers[bwo, c.BH_Delta] + _.headers[bwo - 1, c.BH_CVD]
            )
        else:
            _.headers[bwo, c.BH_CVD] = _.headers[bwo, c.BH_Delta]

    def _update_vwap_and_bands(
        self, nPrice: int64, nQty: int64, bwo: int
    ) -> None:
        """Update Volume Weighted Average Price (VWAP) and rolling standard deviation bands."""
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
