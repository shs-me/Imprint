from abc import ABC, abstractmethod
from math import sqrt
from multiprocessing.synchronize import Event

import numpy as np
from numba import njit
from numpy.typing import NDArray

from .... import AgentManager
from ....settings import BarHeaders as chs  # noqa: F401
from ....settings import SpaceCoords as spc
from ....settings import StateFlags as stf
from .. import ConvertMetrics, HeadersGet


class FootprintReader(ABC):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        self.manager, self.send_signal = manager, execution_event
        self.set_status = manager.set_status
        # Footprint
        self.last_box, self.last_idx = 0, 0
        self.cfgFootprint = self.manager.cfgFootprint
        self.flag_buf: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.flag : self.cfgFootprint.flag + 1
        ]
        self.base_price_and_timestamp_buf: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.basePrice[0] : self.cfgFootprint.baseTimestamp[1]
        ].cast("q")
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self._init_array()

    def _init_array(self) -> None:
        self.footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint)],
        )
        self.footprint_state: NDArray[np.int32] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int32,
        )
        self.footprint_state.fill(0)
        #  - - -
        self.headers: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.headers)
        ].cast("q")
        #  - - -
        self.space_1: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_1)
        ].cast("q")
        self.space_2: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_2)
        ].cast("q")

    def init_session(self) -> None:
        nBasePrice, baseTimestamp = self.base_price_and_timestamp_buf[:]
        self.con: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par,
            footprint=self.footprint,
            headers_buf=self.headers,
            cfgFootprint=self.cfgFootprint,
        )
        self.ind = HeadersGet(converter=self.con)
        self.con.init_session(price=nBasePrice, timestamp=baseTimestamp)

    def check_update(self) -> None:
        self._update_state()
        self.check_pattern()

    @abstractmethod
    def check_pattern(self):
        pass

    def _update_state(self):
        old_flag: int = 1 if self.flag_buf[0] == 0 else 0
        self.last_box = self.flag_buf[0]
        space = self.space_1 if old_flag == 0 else self.space_2
        IDYmin, IDXmin = space[spc.IDYmin], space[spc.IDXmin]
        IDYmax, IDXmax = space[spc.IDYmax], space[spc.IDXmax]
        self._update_cluster(IDYmin=IDYmin, IDYmax=IDYmax, IDXmin=IDXmin, IDXmax=IDXmax)
        self._update_footprint_realtime_state(IDYmin=IDYmin, IDYmax=IDYmax)
        for idx in range((IDXmin & ~1), IDXmax, 2):
            idxBid, idxAsk = idx, idx + 1
            self._update_bid_ask_state(
                IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
            )
            self._update_bar_state(
                IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
            )
            if idx > self.last_idx:
                self.last_idx = idx
                self._update_footprint_static_state(idx=idx)

        # - - -
        # reset
        space[spc.IDYmin], space[spc.IDXmin] = self.con.lines, self.con.footprintCols
        space[spc.IDYmax], space[spc.IDXmax] = 0, 0

    # - - Cluster - -
    def _update_cluster(
        self, IDYmin: int, IDYmax: int, IDXmin: int, IDXmax: int
    ) -> None:
        self._clear_cluster_state(
            IDYmin=IDYmin, IDYmax=IDYmax, IDXmin=IDXmin, IDXmax=IDXmax
        )

    def _clear_cluster_state(
        self, IDYmin: int, IDYmax: int, IDXmin: int, IDXmax: int
    ) -> None:
        indicators = stf.BIG_TRADE
        clear_mask = ~(indicators)
        self.footprint_state[IDYmin:IDYmax, IDXmin:IDXmax] &= clear_mask

    # - - BidAsk  - - -
    def _update_bid_ask_state(
        self, IDYmin: int, IDYmax: int, idxBid: int, idxAsk: int
    ) -> None:
        self._clear_bid_ask_state(IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid)

        idyBid = slice(IDYmin + 1, IDYmax + 1)
        idyAsk = slice(IDYmin, IDYmax)
        self._update_zero_print(
            idyBid=idyBid, idyAsk=idyAsk, idxBid=idxBid, idxAsk=idxAsk
        )
        self._update_delta_domination(
            idyBid=idyBid, idyAsk=idyAsk, idxBid=idxBid, idxAsk=idxAsk
        )
        self._update_imbalance(
            idyBid=idyBid, idyAsk=idyAsk, idxBid=idxBid, idxAsk=idxAsk
        )

    def _clear_bid_ask_state(self, IDYmin: int, IDYmax: int, idxBid: int) -> None:
        indicators = stf.ZERO_PRINT | stf.DELTA_DOMINATION | stf.IMBALANCE
        clear_mask = ~(indicators)

        self.footprint_state[IDYmin : IDYmax + 1, idxBid : idxBid + 2] &= clear_mask

    def _update_zero_print(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        fp_state[idyBid, idxBid][
            ((fp[idyAsk, idxAsk] > 0) & (fp[idyBid, idxBid] == 0))
        ] |= stf.ZERO_PRINT

        fp_state[idyAsk, idxAsk][
            ((fp[idyBid, idxBid] > 0) & (fp[idyAsk, idxAsk] == 0))
        ] |= stf.ZERO_PRINT

    def _update_delta_domination(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        fp_state[idyBid, idxBid][((fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) < 0)] |= (
            stf.DELTA_DOMINATION
        )

        fp_state[idyAsk, idxAsk][((fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) > 0)] |= (
            stf.DELTA_DOMINATION
        )

    def _update_imbalance(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        fp_state[idyBid, idxBid][(fp[idyBid, idxBid] > (fp[idyAsk, idxAsk] * 3))] |= (
            stf.IMBALANCE
        )

        fp_state[idyAsk, idxAsk][(fp[idyAsk, idxAsk] > (fp[idyBid, idxBid] * 3))] |= (
            stf.IMBALANCE
        )

    # - - Bar  - -
    def _update_bar_state(
        self, IDYmin: int, IDYmax: int, idxBid: int, idxAsk: int
    ) -> None:
        ind = self.ind
        #  - - -
        open, close = ind.openPrice(idxBid), ind.closePrice(idxBid)
        high, low = ind.highPrice(idxBid), ind.lowPrice(idxBid)

        self._clear_bar_state(high=high, low=low, idxBid=idxBid)
        self._update_ohlc(idxBid=idxBid, open=open, high=high, low=low, close=close)
        self._update_poc_va_bar(high=high, low=low, idxBid=idxBid)

    def _clear_bar_state(self, high: int, low: int, idxBid: int) -> None:
        headers = stf.OPEN | stf.HIGH | stf.LOW | stf.CLOSE
        indicators = stf.POC_BAR | stf.VA_MIN_BAR | stf.VA_MAX_BAR
        clear_mask = ~(headers | indicators)
        self.footprint_state[high : low + 1, idxBid] &= clear_mask

    def _update_ohlc(
        self, open: int, high: int, low: int, close: int, idxBid: int
    ) -> None:
        self.footprint_state[open, idxBid] |= stf.OPEN
        self.footprint_state[high, idxBid] |= stf.HIGH
        self.footprint_state[low, idxBid] |= stf.LOW
        self.footprint_state[close, idxBid] |= stf.CLOSE

    def _update_poc_va_bar(self, high: int, low: int, idxBid: int) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        vp_bar = fp[high : low + 1, idxBid] + fp[high : low + 1, idxBid + 1]
        poc = np.argmax(vp_bar)
        va_max, va_min = calc_value_area(vp_slice=vp_bar, center_idx=poc)
        fp_state[poc, idxBid] |= stf.POC_BAR
        fp_state[va_max, idxBid] |= stf.VA_MAX_BAR
        fp_state[va_min, idxBid] |= stf.VA_MIN_BAR

    # - - Footprint: RealTime - -
    def _update_footprint_realtime_state(self, IDYmin: int, IDYmax: int) -> None:
        idxLevel = self.con.idxVP
        # - - -
        self._clear_footprint_realtime_state(
            IDYmin=IDYmin, IDYmax=IDYmax, idxLevel=idxLevel
        )
        self._update_delta_dominations_fp(
            IDYmin=IDYmin, IDYmax=IDYmax, idxLevel=idxLevel
        )

    def _clear_footprint_realtime_state(
        self, IDYmin: int, IDYmax: int, idxLevel: int
    ) -> None:
        indicators = stf.BID_DELTA_DOMINATION_FP | stf.ASK_DELTA_DOMINATION_FP
        clear_mask = ~(indicators)
        self.footprint_state[IDYmin:IDYmax, idxLevel] &= clear_mask

    def _update_delta_dominations_fp(
        self, IDYmin: int, IDYmax: int, idxLevel: int
    ) -> None:
        fp, fp_state, idxDP = self.footprint, self.footprint_state, self.con.idxDP
        # - - -
        fp_state[IDYmin:IDYmax, idxLevel][(fp[IDYmin:IDYmax, idxDP] < 0)] |= (
            stf.BID_DELTA_DOMINATION_FP
        )
        fp_state[IDYmin:IDYmax, idxLevel][(fp[IDYmin:IDYmax, idxDP] > 0)] |= (
            stf.ASK_DELTA_DOMINATION_FP
        )

    # - - Footprint: Static - -
    def _update_footprint_static_state(self, idx: int) -> None:
        idxLevel, idxBarrier = self.con.idxVP, self.con.idxDP  # noqa: F841
        # - - -
        high, low = self.ind.highPrice(idx), self.ind.lowPrice(idx)
        self._clear_footprint_static_state(idxLevel=idxLevel)
        self._update_vwap_bb(idxLevel=idxLevel)
        self._update_poc_va_fp(idxLevel=idxLevel)
        self._update_auction(high=high, low=low, idx=idx, idxLevel=idxLevel)

    def _clear_footprint_static_state(self, idxLevel: int) -> None:
        self.footprint_state[:, idxLevel] &= ~(
            stf.VWAP
            | stf.LOWER_BB
            | stf.UPPER_BB
            | stf.POC_BAR
            | stf.VA_MIN_FP
            | stf.VA_MAX_FP
            | stf.UNFINISHED_AUCTION
            | stf.FINISHED_AUCTION
        )

    def _update_vwap_bb(self, idxLevel: int) -> None:
        sum_w, sum_p2w = self.ind.vwap_sum_w(), self.ind.vwap_sum_p2w()
        vwap = self.ind.vwap_sum_pw() / sum_w
        std_dev = sqrt(max(0.0, (sum_p2w / sum_w) - (vwap**2)))
        upper_bb, lower_bb = vwap + (2 * std_dev), vwap - (2 * std_dev)
        self.footprint_state[self.con.to_idy(round(vwap)), idxLevel] |= stf.VWAP
        self.footprint_state[self.con.to_idy(round(upper_bb)), idxLevel] |= stf.UPPER_BB
        self.footprint_state[self.con.to_idy(round(lower_bb)), idxLevel] |= stf.LOWER_BB

    def _update_poc_va_fp(self, idxLevel: int) -> None:
        fp, fp_state, idxVP = self.footprint, self.footprint_state, self.con.idxVP
        # - - -
        poc = np.argmax(fp[:, idxVP])
        va_max, va_min = calc_value_area(vp_slice=fp[:, idxVP], center_idx=poc)
        fp_state[poc, idxLevel] |= stf.POC_FP
        fp_state[va_max, idxLevel] |= stf.VA_MAX_FP
        fp_state[va_min, idxLevel] |= stf.VA_MIN_FP

    def _update_auction(self, high: int, low: int, idx: int, idxLevel: int) -> None:
        fp = self.footprint
        # - - -
        self.footprint_state[high, idxLevel] = (
            stf.FINISHED_AUCTION if fp[high, idx + 1] == 0 else stf.UNFINISHED_AUCTION
        )
        self.footprint_state[low, idxLevel] = (
            stf.FINISHED_AUCTION if fp[low, idx] == 0 else stf.UNFINISHED_AUCTION
        )

    # - - Pattern - -
    def _mask_closeBar(self, idx: int | None) -> None | NDArray[np.int32]:
        idx_ = self.con.get_Bar_id(idx) * 2
        if (idx_ := self.con.get_Bar_id(idx) * 2) != 0:
            return self.footprint_state[:, idx_ - 2] & (
                stf.HIGH
                | stf.LOW
                | stf.CLOSE
                | stf.POC_BAR
                | stf.VA_MAX_BAR
                | stf.VA_MIN_BAR
            )

    def P_shape(self, idx: int | None = None, bullish: bool = True) -> bool:
        if (closeBar := self._mask_closeBar(idx=idx)) is not None:
            high, low = (closeBar & stf.HIGH).argmax(), (closeBar & stf.LOW).argmax()
            va_min = (closeBar & stf.VA_MIN_BAR).argmax()
            close = (closeBar & stf.CLOSE).argmax()
            if (closeBar & stf.OPEN).argmax() > va_min:
                if (va_min - high) > ((low - high) * 0.3):
                    if bullish:
                        if (closeBar & stf.VA_MAX_BAR).argmax() >= close:
                            if self.auction(idy=high, finished=False):
                                return True
                    else:
                        if close > va_min:
                            if self.auction(idy=high, finished=True):
                                return True

        return False

    def b_shape(self, idx: int | None = None, bearish: bool = True) -> bool:
        if (closeBar := self._mask_closeBar(idx=idx)) is not None:
            high, low = (closeBar & stf.HIGH).argmax(), (closeBar & stf.LOW).argmax()
            va_max = (closeBar & stf.VA_MAX_BAR).argmax()
            close = (closeBar & stf.CLOSE).argmax()
            if va_max > (closeBar & stf.OPEN).argmax():
                if (low - va_max) > ((low - high) * 0.3):
                    if bearish:
                        if (closeBar & stf.VA_MIN_BAR).argmax() <= close:
                            if self.auction(idy=low, finished=False):
                                return True
                    else:
                        if va_max > close:
                            if self.auction(idy=low, finished=True):
                                return True
        return False

    def auction(self, idy: int | np.intp, finished: bool) -> bool:
        return bool(
            self.footprint_state[idy, self.con.idxVP] & stf.FINISHED_AUCTION
            if finished
            else stf.UNFINISHED_AUCTION
        )


@njit(cache=True)
def calc_value_area(vp_slice: NDArray[np.int64], center_idx) -> tuple[int, int]:
    target_vol, current_vol = np.sum(vp_slice) * 0.70, vp_slice[center_idx]
    up_idx, down_idx, max_len = center_idx - 1, center_idx + 1, len(vp_slice)
    while current_vol < target_vol:
        if 0 <= up_idx - 1 or down_idx + 1 < max_len:
            vol_up = vp_slice[up_idx - 1] if 0 <= up_idx - 1 else 0
            vol_down = vp_slice[down_idx + 1] if down_idx + 1 < max_len else 0
            if vol_up > vol_down:
                current_vol += vol_up
                up_idx -= 1
            elif vol_down > vol_up:
                current_vol += vol_down
                down_idx += 1
            else:
                up_idx -= 1
                current_vol += vol_down + vol_up
                down_idx += 1
        else:
            break

    return up_idx + 1, down_idx - 1
