from __future__ import annotations

from dataclasses import dataclass, field
from typing import final, override

import numba as nb
import numpy as np
from numba import njit
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import int64, intp
from numpy.typing import NDArray

import imprint._core.footprint.engine.writer as w
from imprint._core import constant as c
from imprint._core.footprint.engine.base import JitStorage
from imprint._core.utils import FPArray


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

    @final
    @override
    def child_init_array(self, nPrice: int64) -> None:
        """Initialize arrays and instantiate the internal JIT analyzer.

        Parameters
        ----------
        nPrice : int64
            Total number of price levels allocated in the footprint matrix buffer. Must be strictly positive.
        """
        w.Writer.child_init_array(self, nPrice)

        if not (self.re_init & c.RIF_idy):
            self.analyzer = JitFootprintAnalyzer(
                storage=self.storage,
                atr_period=self.strategy.atr_period,
                park_period=self.strategy.park_period,
                ma_vol_period=self.strategy.ma_volume_period,
                ma_ats_period=self.strategy.ma_avg_trade_size_period,
                ma_count_trade_period=self.strategy.ma_count_trade_period,
                big_cluster_mult=round(self.strategy.big_cluster_mult * 10_000),
            )

    @final
    def analyze_footprint(self) -> None:
        """Analyze the current active footprint state, clusters, and bars.

        Updates the active cluster delta domination, updates OHLC/POC/VA bar levels,
        and finalizes closed bars in the underlying storage structures.
        """
        self.re_init: int

        idx, lidx = self.idx[0], self.lidx[0]
        if not self.bbox_is_read():
            self.analyzer.analyze_bar(self.fp.base, self.fp.state)
            self.strategy.on_bar_update(
                self.idYmin[0], self.idYmax[0], idx, lidx
            )

            self.idYmin[0], self.idYmax[0] = self.fp.con.fp_rows[0], 0

        if (self.re_init & c.RIF_idx) or ((idx & ~1) > lidx):
            self.analyzer.analyze_closed_bar(self.fp.base, self.fp.state)
            self.strategy.on_bar_close(idx, lidx)
            if (idx & ~1) > lidx:
                self.lidx[0] = idx & ~1

        self.__set_last_trade_time()

    @final
    def bbox_is_read(self) -> bool:
        """Check if the active footprint's bounding box has been fully evaluated.

        Returns
        -------
        bool
            True if the bounding box represents a fully evaluated state, False otherwise.
        """
        return (self.idYmin[0] == self.fp.con.fp_rows[0]) and (
            self.idYmax[0] == 0
        )

    @final
    def is_bbox_mode(self) -> bool:
        """Determine if the engine is operating in bounding-box block update mode.

        Returns
        -------
        bool
            True if tick-by-tick real-time analysis is disabled and no re-initialization
            session or bar bounds are requested.
        """
        return (
            (not self.strategy.tick_by_tick_analyze)
            and (not (self.re_init & c.RIF_session))
            and (not ((self.idx[0] & ~1) > self.lidx[0]))
        )

    @final
    def __set_last_trade_time(self) -> None:
        if time := self.fp[self.idx[0]].ind.last_trade_time:
            self.trade_read_time[0] = int(time)

    @final
    def final_analyze(self) -> None:
        """Run terminal analyses on the current active bar upon session termination.

        Forces active bar closure routines, updates indicators, and notifies
        the algorithm state machines.
        """
        self.analyzer.analyze_closed_bar(self.fp.base, self.fp.state)
        self.strategy.on_bar_close(self.idx[0], self.lidx[0])
        self.__set_last_trade_time()


spec = [  # pyright: ignore[reportUnknownVariableType]
    ("storage", JitStorage.class_type.instance_type),  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    ("atr_period", nb.int64),
    ("park_period", nb.int64),
    ("ma_vol_period", nb.int64),
    ("ma_ats_period", nb.int64),
    ("ma_count_trade_period", nb.int64),
    ("big_cluster_mult", nb.int64),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitFootprintAnalyzer:
    """Numba JIT-compiled engine responsible for numerical footprint analysis.

    Parameters
    ----------
    storage : JitStorage
        Underlying memory buffer and header repository storing raw and analyzed state.
    atr_period : int
        Lookback window for Average True Range calculation.
    park_period : int
        Lookback window for Parkinson volatility computation.
    ma_vol_period : int
        Moving average period for volume smoothing.
    ma_ats_period : int
        Moving average period for average trade size smoothing.
    ma_count_trade_period : int
        Moving average period for trade count smoothing.
    big_cluster_mult : int
        Multiplicative threshold factor scaled by 10,000 for detecting big clusters.

    Attributes
    ----------
    storage : JitStorage
        Underlying memory buffer and header repository storing raw and analyzed state.
    atr_period : int
        Lookback window for Average True Range calculation.
    park_period : int
        Lookback window for Parkinson volatility computation.
    ma_vol_period : int
        Moving average period for volume smoothing.
    ma_ats_period : int
        Moving average period for average trade size smoothing.
    ma_count_trade_period : int
        Moving average period for trade count smoothing.
    big_cluster_mult : int
        Multiplicative threshold factor scaled by 10,000 for detecting big clusters.
    """

    def __init__(
        self,
        storage: JitStorage,
        atr_period: int,
        park_period: int,
        ma_vol_period: int,
        ma_ats_period: int,
        ma_count_trade_period: int,
        big_cluster_mult: int,
    ) -> None:
        self.storage: JitStorage = storage
        self.atr_period: int = atr_period
        self.park_period: int = park_period
        self.ma_vol_period: int = ma_vol_period
        self.ma_ats_period: int = ma_ats_period
        self.ma_count_trade_period: int = ma_count_trade_period
        self.big_cluster_mult: int = big_cluster_mult

    def analyze_bar(self, fp: FPArray, fp_state: FPArray) -> None:
        """Update microstructural states, OHLC flags, imbalance, and bar Value Area.

        Parameters
        ----------
        fp : FPArray
            2D footprint base array of shape ``(N, M)`` representing volume profile matrix.
        fp_state : FPArray
            2D footprint state bitmask array of shape ``(N, M)`` for tracking features and flags.
        """
        _ = self.storage
        # - - -
        lidx: int = _.lidx[0]
        idXbid: int = lidx
        idXask: int = idXbid + 1
        bar: int = idXbid // 2
        bwo: int = _.headers_offset[0] + bar

        if _.headers[bwo, c.BH_Volume] == 0:
            return

        openNprice: int64 = _.headers[bwo, c.BH_Open]
        highNprice: int64 = _.headers[bwo, c.BH_High]
        lowNprice: int64 = _.headers[bwo, c.BH_Low]
        closeNprice: int64 = _.headers[bwo, c.BH_Close]

        bNprice, step_tick = _.baseNprice[0], _.step_tick
        scale, center = _.scale, _.center[0]

        open_idy: int64 = (bNprice - openNprice) // scale + center
        high_idy: int64 = (bNprice - highNprice) // scale + center
        low_idy: int64 = (bNprice - lowNprice) // scale + center
        close_idy: int64 = (bNprice - closeNprice) // scale + center

        vp_bar: NDArray[int64] = (
            fp[high_idy : low_idy + 1, idXbid]
            + fp[high_idy : low_idy + 1, idXask]
        )
        poc: intp = np.argmax(vp_bar)
        vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
        _.headers[bwo, c.BH_POC] = (center - (high_idy + poc)) * scale + bNprice
        _.headers[bwo, c.BH_VAH] = (center - (high_idy + vah)) * scale + bNprice
        _.headers[bwo, c.BH_VAL] = (center - (high_idy + val)) * scale + bNprice

        if not _.with_state:
            return

        idYmin, idYmax = _.idYmin[0], _.idYmax[0]

        state1 = c.SF_OPEN | c.SF_HIGH | c.SF_LOW | c.SF_CLOSE
        state2 = c.SF_POC_BAR | c.SF_VAL_BAR | c.SF_VAH_BAR
        fp_state[high_idy : low_idy + 1, idXbid] &= ~(state1 | state2)

        fp_state[open_idy, idXbid] |= c.SF_OPEN
        fp_state[high_idy, idXbid] |= c.SF_HIGH
        fp_state[low_idy, idXbid] |= c.SF_LOW
        fp_state[close_idy, idXbid] |= c.SF_CLOSE

        fp_state[(high_idy + poc), idXbid] |= c.SF_POC_BAR
        fp_state[(high_idy + vah), idXbid] |= c.SF_VAH_BAR
        fp_state[(high_idy + val), idXbid] |= c.SF_VAL_BAR

        state3 = c.SF_ZERO_PRINT | c.SF_DELTA_DOMINATION | c.SF_IMBALANCE
        fp_state[idYmin:idYmax, idXbid : idXask + 1] &= ~state3

        state4 = c.SF_BID_DELTA_DOMINATION_FP | c.SF_ASK_DELTA_DOMINATION_FP
        fp_state[idYmin:idYmax, _.idxDP] &= ~(state4)

        ma_vol: int64 | int = (
            _.headers[bwo - 1, c.BH_MA_VOL] if (bwo - 1) > 0 else 0
        )
        vol: int64 = int64(ma_vol * (self.big_cluster_mult / 10_000))
        for idy in range(idYmin, idYmax):
            if ma_vol:
                fp_state[idy, _.idxDP] |= (
                    c.SF_BID_DELTA_DOMINATION_FP
                    if (fp[idy, _.idxDP] < 0)
                    else c.SF_ASK_DELTA_DOMINATION_FP
                )

                for idx in range(lidx, lidx + 2):
                    if (not (fp_state[idy, idx] & c.SF_BIG_CLUSTER)) and (
                        fp[idy, idx] > vol
                    ):
                        fp_state[idy, idx] |= c.SF_BIG_CLUSTER

            bid_val, ask_val = fp[idy, idXbid], fp[idy, idXask]

            if (ask_val > 0) and (bid_val == 0):
                fp_state[idy, idXbid] |= c.SF_ZERO_PRINT

            elif (bid_val > 0) and (ask_val == 0):
                fp_state[idy, idXask] |= c.SF_ZERO_PRINT

            if bid_val > ask_val:
                fp_state[idy, idXbid] |= c.SF_DELTA_DOMINATION

            elif ask_val > bid_val:
                fp_state[idy, idXask] |= c.SF_DELTA_DOMINATION

            if step_tick > 1:
                if bid_val > (ask_val * 3):
                    fp_state[idy, idXbid] |= c.SF_IMBALANCE

                elif ask_val > (bid_val * 3):
                    fp_state[idy, idXask] |= c.SF_IMBALANCE
            else:
                ymin, ymax = max(high_idy, idy - 1), min(low_idy, idy + 1)
                if (idy > ymin) and (bid_val > (fp[ymin, idXask] * 3)):
                    fp_state[idy, idXbid] |= c.SF_IMBALANCE
                    fp_state[ymin, idXask] &= ~(c.SF_IMBALANCE)

                if (idy < ymax) and (ask_val > (fp[ymax, idXbid] * 3)):
                    fp_state[idy, idXask] |= c.SF_IMBALANCE
                    fp_state[ymax, idXbid] &= ~(c.SF_IMBALANCE)

    def analyze_closed_bar(self, fp: FPArray, fp_state: FPArray) -> None:
        """Calculate indicator states and footprint flags upon bar closure.

        Computes ATR, Parkinson Volatility, VWAP bands, Point of Control (POC),
        Value Area (VAH/VAL), and auction state flags on bar close.

        Parameters
        ----------
        fp : FPArray
            2D array of shape ``(N, M)`` storing base footprint volume profile matrix.
        fp_state : FPArray
            2D array of shape ``(N, M)`` storing footprint bitmask flags.
        """
        _ = self.storage
        # - - -
        lidx: int = _.lidx[0]
        bar: int = (lidx & ~1) // 2
        bwo: int = _.headers_offset[0] + bar

        if _.headers[bwo, c.BH_Volume] == 0:
            return

        oldBwo: int = bwo - 1

        highNprice: int64 = _.headers[bwo, c.BH_High]
        lowNprice: int64 = _.headers[bwo, c.BH_Low]

        bNprice, idxVP = _.baseNprice[0], _.idxVP
        scale, center = _.scale, _.center[0]

        high_idy: int64 = (bNprice - highNprice) // scale + center
        low_idy: int64 = (bNprice - lowNprice) // scale + center

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

        # PARK
        log_ratio = np.log(highNprice / lowNprice)
        cur_var: int = round((log_ratio * log_ratio) * c.VAR_SCALE)
        if bar > 0:
            pre_var: int64 = _.headers[oldBwo, c.BH_PARK]
            _.headers[bwo, c.BH_PARK] = (
                (pre_var * (self.park_period - 1)) + cur_var
            ) // self.park_period
        else:
            _.headers[bwo, c.BH_PARK] = cur_var

        bar_max = bwo

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
            _.headers[bwo, c.BH_MA_ATS] = int64(
                (
                    _.headers[bar_min:bar_max, c.BH_Volume]
                    // _.headers[bar_min:bar_max, c.BH_CountTrade]
                ).mean()
            )

        # Update POC + VA
        poc: intp = np.argmax(fp[:, idxVP])
        vah, val = calc_value_area(vp_slice=fp[:, idxVP], center_idx=poc)
        _.headers[bwo, c.BH_POC_FP] = (center - poc) * scale + bNprice
        _.headers[bwo, c.BH_VAH_FP] = (center - vah) * scale + bNprice
        _.headers[bwo, c.BH_VAL_FP] = (center - val) * scale + bNprice

        if not _.with_state:
            return

        fp_state[poc, lidx] |= c.SF_POC_FP
        fp_state[vah, lidx] |= c.SF_VAH_FP
        fp_state[val, lidx] |= c.SF_VAL_FP

        state = c.SF_UNFINISHED_AUCTION | c.SF_FINISHED_AUCTION
        fp_state[high_idy : low_idy + 1, idxVP] &= ~(state)

        # Update VWAP+BB
        vwap = (bNprice - _.headers[bwo, c.BH_VWAP]) // scale + center
        vwap_bb_lower = (
            bNprice - _.headers[bwo, c.BH_VWAP_LOWER_BAND]
        ) // scale + center
        vwap_bb_upper = (
            bNprice - _.headers[bwo, c.BH_VWAP_UPPER_BAND]
        ) // scale + center

        if 0 <= vwap < fp_state.shape[0]:
            fp_state[vwap, lidx] |= c.SF_VWAP_FP
        if 0 <= vwap_bb_upper < fp_state.shape[0]:
            fp_state[vwap_bb_upper, lidx] |= c.SF_UPPER_BAND_FP
        if 0 <= vwap_bb_lower < fp_state.shape[0]:
            fp_state[vwap_bb_lower, lidx] |= c.SF_LOWER_BAND_FP

        # Update Auction
        high_finished, low_finished = (
            fp[high_idy, lidx + 1] == 0,
            fp[low_idy, lidx] == 0,
        )
        highAuction = (
            c.SF_FINISHED_AUCTION if high_finished else c.SF_UNFINISHED_AUCTION
        )
        lowAuction = (
            c.SF_FINISHED_AUCTION if low_finished else c.SF_UNFINISHED_AUCTION
        )
        fp_state[high_idy, idxVP] |= highAuction
        fp_state[low_idy, idxVP] |= lowAuction


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
