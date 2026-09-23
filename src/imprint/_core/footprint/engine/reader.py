from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import bool_, int64, intp
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.footprint.engine import writer as w


@dataclass(slots=True)
class Reader(w.Writer):
    last_idx: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @final
    @override
    def child_init_idx(self, nPrice: int64, timestamp: int64) -> None:
        w.Writer.child_init_idx(self, nPrice, timestamp)

        self.last_idx[0] = 0

    @final
    def analyze_footprint(self) -> None:
        if not self._bbox_is_readed():
            idYmin, idXmin, idYmax, idXmax = self.bbox
            if self.with_state:
                self.__update_clusters(idYmin, idYmax, idXmin, idXmax)

            for idx in range((idXmin & ~1), idXmax, 2):
                idxBid, idxAsk = idx, idx + 1
                if idx > self.last_idx[0]:
                    self.__update_closed_bar_and_fp()
                    self.last_idx[0] = idx

                self.__update_bar(idYmin, idYmax, idxBid, idxAsk)

            self.bbox[:] = self.bbox_default_value

        if self.re_init & c.RIF_idx:
            self.__update_closed_bar_and_fp()

        self.__set_last_trade_time()

    @final
    def _bbox_is_readed(self) -> bool:
        return bool(np.all(self.bbox == self.bbox_default_value))

    @final
    def __set_last_trade_time(self) -> None:
        if self.fp.bar[self.last_idx[0]].ind.last_trade_time:
            self.trade_read_time[0] = int(
                self.fp.bar[self.last_idx[0]].ind.last_trade_time
            )

    @final
    def __update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        _update_clusters_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idXmin=idXmin,
            idXmax=idXmax,
            fp=self.fp.base,
            fp_state=self.fp.state,
            headers=self.fp.headers,
            headers_offset=self.fp.headers_offset,
            args=self._args,
        )
        self.algorithm.on_clusters_update(idYmin, idYmax, idXmin, idXmax)

    @final
    def __update_closed_bar_and_fp(self) -> None:
        _update_closed_bar_and_fp_states(
            lidx=self.last_idx[0],
            fp=self.fp.base,
            fp_state=self.fp.state,
            headers=self.fp.headers,
            headers_offset=self.fp.headers_offset,
            args=self._args,
        )
        self.algorithm.on_bar_close()

    @final
    def __update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        _update_bar_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idxBid=idxBid,
            idxAsk=idxAsk,
            fp=self.fp.base,
            fp_state=self.fp.state,
            headers=self.fp.headers,
            headers_offset=self.fp.headers_offset,
            args=self._args,
        )
        self.algorithm.on_bar_update(idYmin, idYmax, idxBid, idxAsk)

    @final
    def final_analyze(self) -> None:
        self.__update_closed_bar_and_fp()
        self.__set_last_trade_time()


@njit(cache=True)
def _update_clusters_states(
    idYmin: int64,
    idYmax: int64,
    idXmin: int64,
    idXmax: int64,
    fp: NDArray[int64],
    fp_state: NDArray[int64],
    headers: NDArray[int64],
    headers_offset: memoryview,
    args: NDArray[int64],
) -> None:
    """
    Recalculate delta domination and big trade flags across footprint cluster regions.

    Parameters
    ----------
    idYmin : int64
        Minimum Y-axis row index of modified footprint slice.
    idYmax : int64
        Maximum Y-axis row index of modified footprint slice (exclusive).
    idXmin : int64
        Minimum X-axis column index of modified footprint slice.
    idXmax : int64
        Maximum X-axis column index of modified footprint slice (exclusive).
    fp : NDArray[int64]
        2D array storing base footprint volume profile and delta values.
    fp_state : NDArray[int64]
        2D state array storing calculated bitmask flags for footprint cells.
    headers : NDArray[int64]
        2D array storing bar header data.
    headers_offset : memoryview
        Single-element int64 memory view of active header write offset.
    args : NDArray[int64]
        1D array containing scaled constants, array index mappings, and converter configurations.
    """

    bar: int64 = (idXmax - 1) // 2
    bwo: int64 = headers_offset[0] + bar

    if headers[bwo, c.BH_Volume] == 0:
        return

    state1 = c.SF_BID_DELTA_DOMINATION_FP | c.SF_ASK_DELTA_DOMINATION_FP
    fp_state[idYmin:idYmax, args[w.FU_idxVP]] &= ~(state1)

    bidDD: NDArray[bool_] = fp[idYmin:idYmax, args[w.FU_idxDP]] < 0
    askDD: NDArray[bool_] = fp[idYmin:idYmax, args[w.FU_idxDP]] > 0
    fp_state[idYmin:idYmax, args[w.FU_idxVP]][bidDD] |= (
        c.SF_BID_DELTA_DOMINATION_FP
    )
    fp_state[idYmin:idYmax, args[w.FU_idxVP]][askDD] |= (
        c.SF_ASK_DELTA_DOMINATION_FP
    )

    ma_vol: int64 = headers[bwo - 1, c.BH_MA_VOL]
    if ma_vol:
        vol: int64 = int64(ma_vol * (args[w.FU_big_cluster_mult] / 10_000))

        for idy in range(idYmin, idYmax):
            for idx in range(idXmin, idXmax):
                if (not (fp_state[idy, idx] & c.SF_BIG_CLUSTER)) and (
                    fp[idy, idx] > vol
                ):
                    fp_state[idy, idx] |= c.SF_BIG_CLUSTER


@njit(cache=True)
def _update_closed_bar_and_fp_states(
    lidx: int,
    headers: NDArray[int64],
    headers_offset: memoryview,
    fp: NDArray[int64],
    fp_state: NDArray[int64],
    args: NDArray[int64],
) -> None:
    """
    Calculate indicator states and footprint flags upon bar closure.

    Computes ATR, Parkinson Volatility, VWAP bands, Point of Control (POC),
    Value Area (VAH/VAL), and auction state flags on bar close.

    Parameters
    ----------
    lidx : int
        Column index of closed bar bid column (`last_idx`).
    headers : NDArray[int64]
        2D array holding bar header metrics and metadata.
    headers_offset : memoryview
        Single-element int64 memory view maintaining header offset position.
    fp : NDArray[int64]
        2D array storing base footprint volume profile matrix.
    fp_state : NDArray[int64]
        2D array storing footprint bitmask flags.
    args : NDArray[int64]
        1D array containing scaled constants, array index mappings, and converter configurations.
    """

    bar: int = (lidx & ~1) // 2
    bwo: int = headers_offset[0] + bar

    if headers[bwo, c.BH_Volume] == 0:
        return

    oldBwo: int = bwo - 1

    highNprice: int64 = headers[bwo, c.BH_High]
    lowNprice: int64 = headers[bwo, c.BH_Low]

    bNprice, idxVP = args[w.FU_baseNprice], args[w.FU_idxVP]
    scale, center = args[w.FU_scale], args[w.FU_center]

    high_idy: int64 = (bNprice - highNprice) // scale + center
    low_idy: int64 = (bNprice - lowNprice) // scale + center

    # ATR
    if bar > 0:
        pre_c, pre_atr = headers[oldBwo, c.BH_Close], headers[oldBwo, c.BH_ATR]
        tr: int64 = max(
            highNprice - lowNprice,
            abs(highNprice - pre_c),
            abs(lowNprice - pre_c),
        )
        atr_period = args[w.FU_atr_period]
        headers[bwo, c.BH_ATR] = (
            (pre_atr * (atr_period - 1)) + tr
        ) // atr_period
    else:
        headers[bwo, c.BH_ATR] = highNprice - lowNprice

    # PARK
    log_ratio = np.log(highNprice / lowNprice)
    cur_var: int = round((log_ratio * log_ratio) * c.VAR_SCALE)
    if bar > 0:
        pre_var: int64 = headers[oldBwo, c.BH_PARK]
        park_period = args[w.FU_park_period]
        headers[bwo, c.BH_PARK] = (
            (pre_var * (park_period - 1)) + cur_var
        ) // park_period
    else:
        headers[bwo, c.BH_PARK] = cur_var

    bar_max = bwo

    # MA Volume
    period: int64 = args[w.FU_ma_vol_period]
    bar_min: int | int64 = max(0, bwo - period)
    if (bar_max - bar_min) >= period:
        headers[bwo, c.BH_MA_VOL] = int64(
            headers[bar_min:bar_max, c.BH_Volume].mean()
        )

    # MA Count Trade
    period = args[w.FU_ma_count_trade_period]
    bar_min = max(0, bwo - period)
    if (bar_max - bar_min) >= period:
        headers[bwo, c.BH_MA_COUNT_TRADE] = int64(
            headers[bar_min:bar_max, c.BH_CountTrade].mean()
        )

    # MA Avg Trade Size
    period = args[w.FU_ma_ats_period]
    bar_min = max(0, bwo - period)
    if (bar_max - bar_min) >= period:
        headers[bwo, c.BH_MA_ATS] = int64(
            (
                headers[bar_min:bar_max, c.BH_Volume]
                // headers[bar_min:bar_max, c.BH_CountTrade]
            ).mean()
        )

    # Update POC + VA
    poc: intp = np.argmax(fp[:, idxVP])
    vah, val = calc_value_area(vp_slice=fp[:, idxVP], center_idx=poc)
    headers[bwo, c.BH_POC_FP] = (center - poc) * scale + bNprice
    headers[bwo, c.BH_VAH_FP] = (center - vah) * scale + bNprice
    headers[bwo, c.BH_VAL_FP] = (center - val) * scale + bNprice

    if not args[w.FU_with_state]:
        return

    fp_state[poc, lidx] |= c.SF_POC_FP
    fp_state[vah, lidx] |= c.SF_VAH_FP
    fp_state[val, lidx] |= c.SF_VAL_FP

    state = c.SF_UNFINISHED_AUCTION | c.SF_FINISHED_AUCTION
    fp_state[high_idy : low_idy + 1, idxVP] &= ~(state)

    # Update VWAP+BB
    vwap = (bNprice - headers[bwo, c.BH_VWAP]) // scale + center
    vwap_bb_lower = (
        bNprice - headers[bwo, c.BH_VWAP_LOWER_BAND]
    ) // scale + center
    vwap_bb_upper = (
        bNprice - headers[bwo, c.BH_VWAP_UPPER_BAND]
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


@njit(cache=True)
def _update_bar_states(
    idYmin: int64,
    idYmax: int64,
    idxBid: int,
    idxAsk: int,
    fp: NDArray[int64],
    fp_state: NDArray[int64],
    headers: NDArray[int64],
    headers_offset: memoryview,
    args: NDArray[int64],
) -> None:
    """
    Update microstructural states, OHLC flags, imbalance, and bar Value Area for active bar.

    Parameters
    ----------
    idYmin : int64
        Minimum Y-axis row index in bounding box.
    idYmax : int64
        Maximum Y-axis row index in bounding box.
    idxBid : int
        Grid column index for active bar bid volume.
    idxAsk : int
        Grid column index for active bar ask volume.
    fp : NDArray[int64]
        2D footprint base array.
    fp_state : NDArray[int64]
        2D footprint state bitmask array.
    headers : NDArray[int64]
        2D array storing bar header data.
    headers_offset : memoryview
        Single-element int64 memory view of active header write offset.
    args : NDArray[int64]
        1D array containing scaled constants, array index mappings, and converter configurations.
    """

    bar: int = (idxBid & ~1) // 2
    bwo: int = headers_offset[0] + bar

    if headers[bwo, c.BH_Volume] == 0:
        return

    openNprice: int64 = headers[bwo, c.BH_Open]
    highNprice: int64 = headers[bwo, c.BH_High]
    lowNprice: int64 = headers[bwo, c.BH_Low]
    closeNprice: int64 = headers[bwo, c.BH_Close]

    bNprice, step_tick = args[w.FU_baseNprice], args[w.FU_step_tick]
    scale, center = args[w.FU_scale], args[w.FU_center]

    open_idy: int64 = (bNprice - openNprice) // scale + center
    high_idy: int64 = (bNprice - highNprice) // scale + center
    low_idy: int64 = (bNprice - lowNprice) // scale + center
    close_idy: int64 = (bNprice - closeNprice) // scale + center

    vp_bar: NDArray[int64] = (
        fp[high_idy : low_idy + 1, idxBid] + fp[high_idy : low_idy + 1, idxAsk]
    )
    poc: intp = np.argmax(vp_bar)
    vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
    headers[bwo, c.BH_POC] = (center - (high_idy + poc)) * scale + bNprice
    headers[bwo, c.BH_VAH] = (center - (high_idy + vah)) * scale + bNprice
    headers[bwo, c.BH_VAL] = (center - (high_idy + val)) * scale + bNprice

    if not args[w.FU_with_state]:
        return

    state2 = c.SF_OPEN | c.SF_HIGH | c.SF_LOW | c.SF_CLOSE
    state3 = c.SF_POC_BAR | c.SF_VAL_BAR | c.SF_VAH_BAR
    fp_state[high_idy : low_idy + 1, idxBid] &= ~(state2 | state3)

    fp_state[open_idy, idxBid] |= c.SF_OPEN
    fp_state[high_idy, idxBid] |= c.SF_HIGH
    fp_state[low_idy, idxBid] |= c.SF_LOW
    fp_state[close_idy, idxBid] |= c.SF_CLOSE

    fp_state[(high_idy + poc), idxBid] |= c.SF_POC_BAR
    fp_state[(high_idy + vah), idxBid] |= c.SF_VAH_BAR
    fp_state[(high_idy + val), idxBid] |= c.SF_VAL_BAR

    state1 = c.SF_ZERO_PRINT | c.SF_DELTA_DOMINATION | c.SF_IMBALANCE
    fp_state[idYmin:idYmax, idxBid : idxBid + 2] &= ~state1

    for idy in range(idYmin, idYmax):
        bid_val, ask_val = fp[idy, idxBid], fp[idy, idxAsk]

        if (ask_val > 0) and (bid_val == 0):
            fp_state[idy, idxBid] |= c.SF_ZERO_PRINT

        elif (bid_val > 0) and (ask_val == 0):
            fp_state[idy, idxAsk] |= c.SF_ZERO_PRINT

        if bid_val > ask_val:
            fp_state[idy, idxBid] |= c.SF_DELTA_DOMINATION

        elif ask_val > bid_val:
            fp_state[idy, idxAsk] |= c.SF_DELTA_DOMINATION

        if step_tick > 1:
            if bid_val > (ask_val * 3):
                fp_state[idy, idxBid] |= c.SF_IMBALANCE

            elif ask_val > (bid_val * 3):
                fp_state[idy, idxAsk] |= c.SF_IMBALANCE
        else:
            ymin, ymax = max(high_idy, idy - 1), min(low_idy, idy + 1)
            if (idy > ymin) and (bid_val > (fp[ymin, idxAsk] * 3)):
                fp_state[idy, idxBid] |= c.SF_IMBALANCE
                fp_state[ymin, idxAsk] &= ~(c.SF_IMBALANCE)

            if (idy < ymax) and (ask_val > (fp[ymax, idxBid] * 3)):
                fp_state[idy, idxAsk] |= c.SF_IMBALANCE
                fp_state[ymax, idxBid] &= ~(c.SF_IMBALANCE)


@njit(cache=True)
def calc_value_area(
    vp_slice: NDArray[int64], center_idx: intp
) -> tuple[intp, intp]:
    """
    Compute Value Area High (VAH) and Value Area Low (VAL) bounds covering 70% of total volume.

    Parameters
    ----------
    vp_slice : NDArray[int64]
        1D array slice containing volume profile across price levels.
    center_idx : intp
        Index of Point of Control (POC), representing the peak volume row.

    Returns
    -------
    tuple of (intp, intp)
        Tuple containing `(vah_idx, val_idx)` relative to `vp_slice`.
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
