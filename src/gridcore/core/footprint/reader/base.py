from abc import ABC

import numpy as np
from numba import njit
from numpy import bool_, int32, int64, intp
from numpy.typing import NDArray

from ... import constant as c
from ...ipc import NodeManager
from ...settings import SpaceCoords
from ..models import Converter, FootprintLike


class Reader(ABC):
    def __init__(self, manager: NodeManager) -> None:
        self._manager: NodeManager = manager

        cfgFP = manager.cfgFootprint
        self._bbox_flag: memoryview = cfgFP.bbox_flag
        self._spare_flags: memoryview = cfgFP.spare_flags
        self._base_nPrice: memoryview = cfgFP.base_price.cast("q")
        self._base_timestamp: memoryview = cfgFP.base_timestamp.cast("q")

        cfgMetrics = manager.cfgMetrics
        self._trade_readed_time: memoryview = cfgMetrics.trade_readed_time.cast("q")

        self._init_array()

        self.con: Converter = Converter(
            footprint=self._fp,
            headers=self._headers,
            cfgCoin=manager.cfgCoin,
            cfgFP=cfgFP,
        )
        self.fp: FootprintLike = FootprintLike(
            converter=self.con,
            fp_state=self._fp_state,
            fp_state_cache=self._fp_state_cache,
        )

    def _init_array(self) -> None:
        cfgFP = self._manager.cfgFootprint
        self._fp: NDArray[int64] = np.ndarray(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols),
            dtype=int64,
            buffer=cfgFP.footprint,
        )
        self._fp_state: NDArray[int32] = np.zeros(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols), dtype=int32
        )
        self._headers: NDArray[int64] = np.ndarray(
            shape=(cfgFP.bar_count, c.BH_ConstantCount),
            dtype=int64,
            buffer=cfgFP.headers,
        )
        self._bbox: NDArray[int64] = np.ndarray(
            (2, SpaceCoords._ConstantCount), dtype=int64, buffer=cfgFP.bbox
        )
        self._bbox_default_value: NDArray[int64] = np.array(
            [cfgFP.fp_rows, cfgFP.fp_cols, 0, 0], dtype=int64
        )
        self._fp_state_cache: NDArray[int64] = np.zeros(
            (c.CSD_ConstantCount,), dtype=int64
        )

    def _init_session(self) -> None:
        self._fp_state.fill(0)
        self.last_idx: int = 0
        self.con.init_session(
            price=self._base_nPrice[0], timestamp=self._base_timestamp[0]
        )

    def _update_states(self) -> None:
        oldBuf = 1 if (self._bbox_flag[0] == 0) else 0
        idYmin, idXmin, idYmax, idXmax = self._bbox[oldBuf, :]
        self._update_clusters(idYmin, idYmax, idXmin, idXmax)
        for idx in range((idXmin & ~1), idXmax, 2):
            idxBid, idxAsk = idx, idx + 1
            if self.fp.bar[idx].ind.volume.n > 0:
                if idx > self.last_idx:
                    self._update_closed_bar_and_fp()
                    self._trade_readed_time[0] = int(
                        self.fp.bar[self.last_idx].ind.time.last_trade
                    )
                    self.last_idx = idx

                self._update_bar(idYmin, idYmax, idxBid, idxAsk)

        self._bbox[oldBuf, :] = self._bbox_default_value

    def _update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        _update_clusters_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idXmin=idXmin,
            idXmax=idXmax,
            idxVP=self.con.idxVP,
            idxDP=self.con.idxDP,
            fp=self._fp,
            fp_state=self._fp_state,
        )

    def _update_closed_bar_and_fp(self) -> None:
        _update_closed_bar_and_fp_states(
            lidx=self.last_idx,
            idxVP=self.con.idxVP,
            idxDP=self.con.idxDP,
            hr=self._headers,
            fp=self._fp,
            fp_state=self._fp_state,
            fp_state_cache=self._fp_state_cache,
            nBasePrice=self.con.nBasePrice,
            center=self.con.center,
            scale=self.con.scale,
        )

    def _update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        _update_bar_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idxBid=idxBid,
            idxAsk=idxAsk,
            hr=self._headers,
            fp=self._fp,
            fp_state=self._fp_state,
            nBasePrice=self.con.nBasePrice,
            center=self.con.center,
            scale=self.con.scale,
        )


@njit(cache=True)
def _update_clusters_states(
    idYmin: int64,
    idYmax: int64,
    idXmin: int64,
    idXmax: int64,
    idxVP: int,
    idxDP: int,
    fp: NDArray[int64],
    fp_state: NDArray[int32],
) -> None:
    """Numba JIT kernel recalculating delta domination and big trade flags across clusters."""

    # Clear State's
    state1 = c.SF_BID_DELTA_DOMINATION_FP | c.SF_ASK_DELTA_DOMINATION_FP
    fp_state[idYmin:idYmax, idxVP] &= ~(state1)
    fp_state[idYmin:idYmax, idXmin:idXmax] &= ~(c.SF_BIG_TRADE)

    # Update Delta Domination
    bidDD: NDArray[bool_] = fp[idYmin:idYmax, idxDP] < 0
    askDD: NDArray[bool_] = fp[idYmin:idYmax, idxDP] > 0
    fp_state[idYmin:idYmax, idxVP][bidDD] |= c.SF_BID_DELTA_DOMINATION_FP
    fp_state[idYmin:idYmax, idxVP][askDD] |= c.SF_ASK_DELTA_DOMINATION_FP


@njit(cache=True)
def _update_closed_bar_and_fp_states(
    lidx: int,
    idxVP: int,
    idxDP: int,
    hr: NDArray[int64],
    fp: NDArray[int64],
    fp_state: NDArray[int32],
    fp_state_cache: NDArray[int64],
    nBasePrice: int,
    center: int,
    scale: int,
) -> None:
    """Numba JIT kernel calculating ATR, VWAP, Bollinger Bands, POC, and Value Area on bar closure."""

    bar: int = (lidx & ~1) // 2
    oldBar: int = bar - 1

    highNprice: int64 = hr[bar, c.BH_High]
    lowNprice: int64 = hr[bar, c.BH_Low]

    high_idy: int64 = (nBasePrice - highNprice) // scale + center
    low_idy: int64 = (nBasePrice - lowNprice) // scale + center

    # ATR
    if bar > 0:
        pre_c, pre_atr = hr[oldBar, c.BH_Close], hr[oldBar, c.BH_ATR]
        tr: int64 = max(
            highNprice - lowNprice, abs(highNprice - pre_c), abs(lowNprice - pre_c)
        )
        hr[bar, c.BH_ATR] = ((pre_atr * (c.ATR_PERIOD - 1)) + tr) // c.ATR_PERIOD
    else:
        hr[bar, c.BH_ATR] = highNprice - lowNprice

    # PARK
    log_ratio = np.log(highNprice / lowNprice)
    cur_var: int = round((log_ratio * log_ratio) * c.VAR_SCALE)
    if bar > 0:
        pre_var: int64 = hr[oldBar, c.BH_PARK]
        hr[bar, c.BH_PARK] = (
            (pre_var * (c.PARK_PERIOD - 1)) + cur_var
        ) // c.PARK_PERIOD
    else:
        hr[bar, c.BH_PARK] = cur_var

    # Clear Footprint Static State's
    state_2 = c.SF_POC_FP | c.SF_VAH_FP | c.SF_VAL_FP
    fp_state[fp_state_cache[c.CSD_POC_FP : c.CSD_VAL_FP + 1], idxVP] &= ~(state_2)
    state_3 = c.SF_UNFINISHED_AUCTION | c.SF_FINISHED_AUCTION
    fp_state[high_idy : low_idy + 1, idxVP] &= ~(state_3)

    # Update VWAP+BB
    vwap = (nBasePrice - hr[bar, c.BH_VWAP]) // scale + center
    vwap_bb_lower = (nBasePrice - hr[bar, c.BH_VWAP_LOWER_BAND]) // scale + center
    vwap_bb_upper = (nBasePrice - hr[bar, c.BH_VWAP_UPPER_BAND]) // scale + center

    if 0 <= vwap < fp_state.shape[0]:
        fp_state[fp_state_cache[c.CSD_VWAP], idxVP] &= ~(c.SF_VWAP_FP)
        fp_state[vwap, idxVP] |= c.SF_VWAP_FP
        fp_state_cache[c.CSD_VWAP] = vwap
    if 0 <= vwap_bb_upper < fp_state.shape[0]:
        fp_state[fp_state_cache[c.CSD_UPPER_BB], idxVP] &= ~(c.SF_UPPER_BAND_FP)
        fp_state[vwap_bb_upper, idxVP] |= c.SF_UPPER_BAND_FP
        fp_state_cache[c.CSD_UPPER_BB] = vwap_bb_upper
    if 0 <= vwap_bb_lower < fp_state.shape[0]:
        fp_state[fp_state_cache[c.CSD_LOWER_BB], idxVP] &= ~(c.SF_LOWER_BAND_FP)
        fp_state[vwap_bb_lower, idxVP] |= c.SF_LOWER_BAND_FP
        fp_state_cache[c.CSD_LOWER_BB] = vwap_bb_lower

    # Update POC + VA
    poc: intp = np.argmax(fp[:, idxVP])
    vah, val = calc_value_area(vp_slice=fp[:, idxVP], center_idx=poc)
    fp_state[poc, idxVP] |= c.SF_POC_FP
    fp_state_cache[c.CSD_POC_FP] = poc
    hr[bar, c.BH_POC_FP] = (center - poc) * scale + nBasePrice
    fp_state[vah, idxVP] |= c.SF_VAH_FP
    fp_state_cache[c.CSD_VAH_FP] = vah
    hr[bar, c.BH_VAH_FP] = (center - vah) * scale + nBasePrice
    fp_state[val, idxVP] |= c.SF_VAL_FP
    fp_state_cache[c.CSD_VAL_FP] = val
    hr[bar, c.BH_VAL_FP] = (center - val) * scale + nBasePrice

    # Update Auction
    high_finished, low_finished = fp[high_idy, lidx + 1] == 0, fp[low_idy, lidx] == 0
    highAuction = c.SF_FINISHED_AUCTION if high_finished else c.SF_UNFINISHED_AUCTION
    lowAuction = c.SF_FINISHED_AUCTION if low_finished else c.SF_UNFINISHED_AUCTION
    fp_state[high_idy, idxVP] |= highAuction
    fp_state[low_idy, idxVP] |= lowAuction


@njit(cache=True)
def _update_bar_states(
    idYmin: int64,
    idYmax: int64,
    idxBid: int,
    idxAsk: int,
    hr: NDArray[int64],
    fp: NDArray[int64],
    fp_state: NDArray[int32],
    nBasePrice: int,
    center: int,
    scale: int,
) -> None:
    """Numba JIT kernel calculating active bar OHLC, Zero-Print, Delta Domination, and Imbalances."""

    bar = (idxBid & ~1) // 2

    openNprice: int64 = hr[bar, c.BH_Open]
    highNprice: int64 = hr[bar, c.BH_High]
    lowNprice: int64 = hr[bar, c.BH_Low]
    closeNprice: int64 = hr[bar, c.BH_Close]

    open_idy: int64 = (nBasePrice - openNprice) // scale + center
    high_idy: int64 = (nBasePrice - highNprice) // scale + center
    low_idy: int64 = (nBasePrice - lowNprice) // scale + center
    close_idy: int64 = (nBasePrice - closeNprice) // scale + center

    ymax_climp = min(idYmax + 1, fp.shape[0] - 1)
    idyBid: slice[int64, int64] = slice(idYmin + 1, ymax_climp + 1)
    idyAsk: slice[int64, int64] = slice(idYmin, ymax_climp)

    # Clear State's
    state1 = c.SF_ZERO_PRINT | c.SF_DELTA_DOMINATION | c.SF_IMBALANCE
    fp_state[idYmin:ymax_climp, idxBid : idxBid + 2] &= ~(state1)
    state2 = c.SF_OPEN | c.SF_HIGH | c.SF_LOW | c.SF_CLOSE
    state3 = c.SF_POC_BAR | c.SF_VAL_BAR | c.SF_VAH_BAR
    fp_state[high_idy : low_idy + 1, idxBid] &= ~(state2 | state3)

    # Update ZeroPrint
    bidZP: NDArray[bool_] = (fp[idyAsk, idxAsk] > 0) & (fp[idyBid, idxBid] == 0)
    askZP: NDArray[bool_] = (fp[idyBid, idxBid] > 0) & (fp[idyAsk, idxAsk] == 0)
    fp_state[idyBid, idxBid][bidZP] |= c.SF_ZERO_PRINT
    fp_state[idyAsk, idxAsk][askZP] |= c.SF_ZERO_PRINT

    # Update Delta Domination
    bidDD: NDArray[bool_] = (fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) < 0
    askDD: NDArray[bool_] = (fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) > 0
    fp_state[idyBid, idxBid][bidDD] |= c.SF_DELTA_DOMINATION
    fp_state[idyAsk, idxAsk][askDD] |= c.SF_DELTA_DOMINATION

    # Update IMBALANCE
    bidImb: NDArray[bool_] = fp[idyBid, idxBid] > (fp[idyAsk, idxAsk] * 3)
    askImb: NDArray[bool_] = fp[idyAsk, idxAsk] > (fp[idyBid, idxBid] * 3)
    fp_state[idyBid, idxBid][bidImb] |= c.SF_IMBALANCE
    fp_state[idyAsk, idxAsk][askImb] |= c.SF_IMBALANCE

    # Update OHLC
    fp_state[open_idy, idxBid] |= c.SF_OPEN
    fp_state[high_idy, idxBid] |= c.SF_HIGH
    fp_state[low_idy, idxBid] |= c.SF_LOW
    fp_state[close_idy, idxBid] |= c.SF_CLOSE

    # Update VA + POC
    vp_bar: NDArray[int64] = (
        fp[high_idy : low_idy + 1, idxBid] + fp[high_idy : low_idy + 1, idxAsk]
    )
    poc: intp = np.argmax(vp_bar)
    vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
    hr[bar, c.BH_POC] = (center - (high_idy + poc)) * scale + nBasePrice
    hr[bar, c.BH_VAH] = (center - (high_idy + vah)) * scale + nBasePrice
    hr[bar, c.BH_VAL] = (center - (high_idy + val)) * scale + nBasePrice
    fp_state[(high_idy + poc), idxBid] |= c.SF_POC_BAR
    fp_state[(high_idy + vah), idxBid] |= c.SF_VAH_BAR
    fp_state[(high_idy + val), idxBid] |= c.SF_VAL_BAR


@njit(cache=True)
def calc_value_area(vp_slice: NDArray[int64], center_idx: intp) -> tuple[intp, intp]:
    """Numba JIT kernel computing Value Area High (VAH) and Low (VAL) covering 70% of volume profile."""

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
