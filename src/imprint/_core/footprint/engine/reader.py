from __future__ import annotations

from dataclasses import dataclass, field
from typing import final, override

import numba as nb
import numpy as np
from numba import (
    njit,
    types,  # pyright: ignore[reportPrivateImportUsage]
)
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import bool_, int64, intp
from numpy.typing import NDArray

import imprint._core.constant as c
import imprint._core.footprint.engine.writer as w
from imprint._core.footprint.engine.base import JitStorage


@dataclass(slots=True)
class Reader(w.Writer):
    """Read and analyze market data footprint cluster matrices and bar states.

    This class serves as the core real-time analyzing engine that handles bar
    updates, cluster updates, and indicator calculations on a streaming basis
    by delegating heavy computations to a JIT-compiled analyzer.

    Attributes
    ----------
    analyzer : JitFootprintAnalyzer
        Numba JIT-compiled engine responsible for numerical footprint analysis.
    """

    analyzer: JitFootprintAnalyzer = field(init=False)

    @override
    def __post_init__(self) -> None:
        w.Writer.__post_init__(self)
        self.analyzer = JitFootprintAnalyzer(
            storage=self.storage,
            atr_period=self.strategy.atr_period,
            park_period=self.strategy.park_period,
            ma_vol_period=self.strategy.ma_volume_period,
            ma_ats_period=self.strategy.ma_avg_trade_size_period,
            ma_count_trade_period=self.strategy.ma_count_trade_period,
            big_cluster_vol=self.strategy.big_cluster_vol,
        )

    @override
    def reset(self) -> None:
        w.Writer.reset(self)

        self.analyzer.atr_period = self.strategy.atr_period
        self.analyzer.park_period = self.strategy.park_period
        self.analyzer.ma_vol_period = self.strategy.ma_volume_period
        self.analyzer.ma_ats_period = self.strategy.ma_avg_trade_size_period
        self.analyzer.ma_count_trade_period = (
            self.strategy.ma_count_trade_period
        )
        self.analyzer.big_cluster_vol = self.strategy.big_cluster_vol

    @final
    def analyze_footprint(self) -> None:
        """Analyze the current active footprint state, clusters, and bars.

        Updates the active cluster delta domination, updates OHLC/POC/VA bar levels,
        and finalizes closed bars in the underlying storage structures.
        """
        last_side, last_bar = self.last_side[0], self.fp.last_bar[0]
        if not self.bbox_is_read():
            self.analyzer.analyze_bar()
            self.strategy.on_bar_update(
                self.idYmin[0], self.idYmax[0], last_bar, last_side
            )
            self.reset_bbox()

        if self.closed_bar[0] != self.fp.last_bar[0]:
            self.analyzer.analyze_closed_bar()
            self.strategy.on_bar_close(last_bar, last_side)
            self.closed_bar[0] = self.fp.last_bar[0]

        self.__set_last_trade_time()

    @final
    def bbox_is_read(self) -> bool:
        """Check if the active footprint's bounding box has been fully evaluated."""
        return (self.idYmin[0] == self.fp.con.bar_height[0]) and (
            self.idYmax[0] == 0
        )

    @final
    def is_bbox_mode(self) -> bool:
        """Determine if the engine is operating in bounding-box block update mode."""
        return (not self.strategy.tick_by_tick_analyze) and (
            self.closed_bar[0] == self.fp.last_bar[0]
        )

    @final
    def __set_last_trade_time(self) -> None:
        if time := self.fp[self.fp.last_bar[0]].ind.close_time:
            self.trade_read_time[0] = int(time)

        if self.save_trade_time:
            self.trade_time[0] = 0

    @final
    def final_analyze(self) -> None:
        """Run terminal analyses on the current active bar upon session termination.

        Forces active bar closure routines, updates indicators, and notifies
        the algorithm state machines.
        """
        last_side, last_bar = self.last_side[0], self.fp.last_bar[0]
        if not self.bbox_is_read():
            self.analyzer.analyze_bar()
            self.strategy.on_bar_update(
                self.idYmin[0], self.idYmax[0], last_bar, last_side
            )
            self.reset_bbox()

        self.analyzer.analyze_closed_bar()
        self.strategy.on_bar_close(last_bar, last_side)
        self.__set_last_trade_time()


spec = [  # pyright: ignore[reportUnknownVariableType]
    ("storage", JitStorage.class_type.instance_type),  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    ("atr_period", nb.int64),
    ("park_period", nb.int64),
    ("ma_vol_period", nb.int64),
    ("ma_ats_period", nb.int64),
    ("ma_count_trade_period", nb.int64),
    ("big_cluster_vol", types.MemoryView(nb.int64, 1, "C")),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitFootprintAnalyzer:
    """Numba JIT-compiled engine responsible for numerical footprint analysis."""

    def __init__(
        self,
        storage: JitStorage,
        atr_period: int,
        park_period: int,
        ma_vol_period: int,
        ma_ats_period: int,
        ma_count_trade_period: int,
        big_cluster_vol: memoryview,
    ) -> None:
        self.storage: JitStorage = storage
        self.atr_period: int = atr_period
        self.park_period: int = park_period
        self.ma_vol_period: int = ma_vol_period
        self.ma_ats_period: int = ma_ats_period
        self.ma_count_trade_period: int = ma_count_trade_period
        self.big_cluster_vol: memoryview = big_cluster_vol

    def analyze_bar(self) -> None:
        """Update microstructural states, OHLC flags, imbalance, and bar Value Area."""
        _ = self.storage
        # - - -
        bar: int = _.last_bar[0]
        bwo: int = _.headers_offset[0] + bar

        if _.headers[bwo, c.BH_Volume] == 0:
            return

        openNprice: int64 = _.headers[bwo, c.BH_Open]
        highNprice: int64 = _.headers[bwo, c.BH_High]
        lowNprice: int64 = _.headers[bwo, c.BH_Low]
        closeNprice: int64 = _.headers[bwo, c.BH_Close]

        step_tick, scale, center = _.step_tick[0], _.scale[0], _.center[0]
        bNprice = _.headers[bwo, c.BH_BaseNprice]

        open_idy: int64 = (bNprice - openNprice) // scale + center
        high_idy: int64 = (bNprice - highNprice) // scale + center
        low_idy: int64 = (bNprice - lowNprice) // scale + center
        close_idy: int64 = (bNprice - closeNprice) // scale + center

        # BAR POC, VA
        vp_bar: NDArray[int64] = (
            _.fp[bar, high_idy : low_idy + 1, 0]
            + _.fp[bar, high_idy : low_idy + 1, 1]
        )
        poc: intp = np.argmax(vp_bar)
        vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
        _.headers[bwo, c.BH_POC] = (center - (high_idy + poc)) * scale + bNprice
        _.headers[bwo, c.BH_VAH] = (center - (high_idy + vah)) * scale + bNprice
        _.headers[bwo, c.BH_VAL] = (center - (high_idy + val)) * scale + bNprice

        if not _.with_state[0]:  # Update States
            return

        bid = 2

        clear_state: int = (
            c.SF_OPEN
            | c.SF_HIGH
            | c.SF_LOW
            | c.SF_CLOSE
            | c.SF_POC_BAR
            | c.SF_VAL_BAR
            | c.SF_VAH_BAR
            | c.SF_FINISHED_AUCTION
            | c.SF_UNFINISHED_AUCTION
        )
        _.fp[bar, high_idy : low_idy + 1, bid : bid + 2] &= ~clear_state

        # OHLC
        _.fp[bar, open_idy, bid] |= c.SF_OPEN
        _.fp[bar, high_idy, bid] |= c.SF_HIGH
        _.fp[bar, low_idy, bid] |= c.SF_LOW
        _.fp[bar, close_idy, bid] |= c.SF_CLOSE

        # BAR POC, VA
        _.fp[bar, (high_idy + poc), bid] |= c.SF_POC_BAR
        _.fp[bar, (high_idy + vah), bid] |= c.SF_VAH_BAR
        _.fp[bar, (high_idy + val), bid] |= c.SF_VAL_BAR

        # Finished Auction
        high_finished: bool_ = _.fp[bar, high_idy, 0] == 0
        low_finished: bool_ = _.fp[bar, low_idy, 1] == 0
        _.fp[bar, high_idy, bid] |= (
            c.SF_FINISHED_AUCTION if high_finished else c.SF_UNFINISHED_AUCTION
        )
        _.fp[bar, low_idy, bid + 1] |= (
            c.SF_FINISHED_AUCTION if low_finished else c.SF_UNFINISHED_AUCTION
        )

        # IMBALANCE, DELTA DOMINATION, ZERO PRINT, BIG CLUSTER IN EVERY LEVEL
        idYmin, idYmax = _.idYmin[0], _.idYmax[0]

        clear_state = c.SF_ZERO_PRINT | c.SF_DELTA_DOMINATION | c.SF_IMBALANCE
        _.fp[bar, idYmin:idYmax, bid : bid + 2] &= ~clear_state

        for idy in range(idYmin, idYmax):
            for side in range(2, 4):
                if (not (_.fp[bar, idy, side] & c.SF_BIG_CLUSTER)) and (
                    _.fp[bar, idy, side] >= self.big_cluster_vol[0]
                ):
                    _.fp[bar, idy, side] |= c.SF_BIG_CLUSTER

            bid_val, ask_val = _.fp[bar, idy, 0], _.fp[bar, idy, 1]

            if (ask_val > 0) and (bid_val == 0):
                _.fp[bar, idy, bid] |= c.SF_ZERO_PRINT

            elif (bid_val > 0) and (ask_val == 0):
                _.fp[bar, idy, bid + 1] |= c.SF_ZERO_PRINT

            if bid_val > ask_val:
                _.fp[bar, idy, bid] |= c.SF_DELTA_DOMINATION

            elif ask_val > bid_val:
                _.fp[bar, idy, bid + 1] |= c.SF_DELTA_DOMINATION

            if step_tick > 1:
                if bid_val > (ask_val * 3):
                    _.fp[bar, idy, bid] |= c.SF_IMBALANCE

                elif ask_val > (bid_val * 3):
                    _.fp[bar, idy, bid + 1] |= c.SF_IMBALANCE
            else:
                ymin, ymax = max(high_idy, idy - 1), min(low_idy, idy + 1)
                if (idy > ymin) and (bid_val > (_.fp[bar, ymin, 1] * 3)):
                    _.fp[bar, idy, bid] |= c.SF_IMBALANCE
                    _.fp[bar, ymin, bid + 1] &= ~(c.SF_IMBALANCE)

                if (idy < ymax) and (ask_val > (_.fp[bar, ymax, 1] * 3)):
                    _.fp[bar, idy, bid + 1] |= c.SF_IMBALANCE
                    _.fp[bar, ymax, bid] &= ~(c.SF_IMBALANCE)

    def analyze_closed_bar(self) -> None:
        """Calculate indicator states and footprint flags upon bar closure.

        Computes ATR, Parkinson Volatility, VWAP bands, Point of Control (POC),
        Value Area (VAH/VAL)."""
        _ = self.storage
        # - - -
        bar: int = _.closed_bar[0]
        bwo: int = _.headers_offset[0] + bar

        if _.headers[bwo, c.BH_Volume] == 0:
            return

        highNprice: int64 = _.headers[bwo, c.BH_High]
        lowNprice: int64 = _.headers[bwo, c.BH_Low]

        oldBwo: int = bwo - 1

        # ATR
        if bar > 0:
            pre_c, pre_atr = (
                _.headers[oldBwo, c.BH_Close],
                _.headers[oldBwo, c.BH_ATR],
            )
            tr: int64 = max(
                highNprice - lowNprice,
                abs(highNprice - pre_c),
                abs(lowNprice - pre_c),
            )
            _.headers[bwo, c.BH_ATR] = (
                (pre_atr * (self.atr_period - 1)) + tr
            ) // self.atr_period
        else:
            _.headers[bwo, c.BH_ATR] = highNprice - lowNprice

        # PARKINSON
        log_ratio = np.log(highNprice / lowNprice)
        cur_var: int = round((log_ratio * log_ratio) * c.VAR_SCALE)
        if bar > 0:
            pre_var: int64 = _.headers[oldBwo, c.BH_PARK]
            _.headers[bwo, c.BH_PARK] = (
                (pre_var * (self.park_period - 1)) + cur_var
            ) // self.park_period
        else:
            _.headers[bwo, c.BH_PARK] = cur_var

        bar_max: int = bwo

        # MA Volume
        period: int = self.ma_vol_period
        bar_min: int | int64 = max(0, bwo - period)
        if (bar_max - bar_min) >= period:
            _.headers[bwo, c.BH_MA_VOL] = int64(
                _.headers[bar_min:bar_max, c.BH_Volume].mean()
            )

        # MA Count Trade
        period = self.ma_count_trade_period
        bar_min = max(0, bwo - period)
        if (bar_max - bar_min) >= period:
            _.headers[bwo, c.BH_MA_COUNT_TRADE] = int64(
                _.headers[bar_min:bar_max, c.BH_CountTrade].mean()
            )

        # MA Avg Trade Size
        period = self.ma_ats_period
        bar_min = max(0, bwo - period)
        if (bar_max - bar_min) >= period:
            vols = _.headers[bar_min:bar_max, c.BH_Volume]
            trades = _.headers[bar_min:bar_max, c.BH_CountTrade]
            valid = trades > 0
            if np.any(valid):
                _.headers[bwo, c.BH_MA_ATS] = int64(
                    (vols[valid] // trades[valid]).mean()
                )

        # FP POC, VA
        baseNprice = _.headers[bwo, c.BH_BaseNprice]
        center, scale = _.center[0], _.scale[0]

        poc: intp = np.argmax(_.profile[0, :])
        vah, val = calc_value_area(vp_slice=_.profile[0, :], center_idx=poc)
        _.headers[bwo, c.BH_POC_FP] = (center - poc) * scale + baseNprice
        _.headers[bwo, c.BH_VAH_FP] = (center - vah) * scale + baseNprice
        _.headers[bwo, c.BH_VAL_FP] = (center - val) * scale + baseNprice


@final
@dataclass(slots=True)
class FootprintEngine(Reader): ...  # pyright: ignore[reportUninitializedInstanceVariable]


@njit(cache=True)
def calc_value_area(
    vp_slice: NDArray[int64], center_idx: intp
) -> tuple[intp, intp]:
    """Compute Value Area High (VAH) and Value Area Low (VAL) bounds covering 70% of total volume.

    Parameters
    ----------
    vp_slice : NDArray[int64]
        1D array slice containing volume profile across price levels.
    center_idx : intp
        Index of Point of Control (POC), representing the peak volume row.

    Returns
    -------
    tuple[intp, intp]
        Tuple containing ``(vah_idx, val_idx)`` relative to ``vp_slice``.
    """

    target_vol: float = np.sum(vp_slice) * 0.70
    current_vol: int64 = vp_slice[center_idx]
    max_len: int = len(vp_slice)
    up_idx: intp = center_idx - 1
    down_idx: intp = center_idx + 1
    while current_vol < target_vol:
        if 0 <= up_idx or down_idx < max_len:
            vol_up = vp_slice[up_idx] if 0 <= up_idx else 0
            vol_down = vp_slice[down_idx] if down_idx < max_len else 0
            if vol_up > vol_down:
                up_idx -= 1
                current_vol += vol_up

            elif vol_down > vol_up:
                down_idx += 1
                current_vol += vol_down

            elif vol_up == vol_down:
                if up_idx >= 0:
                    up_idx -= 1
                    current_vol += vol_up

                if down_idx < max_len:
                    down_idx += 1
                    current_vol += vol_down
        else:
            break

    return up_idx + 1, down_idx - 1
