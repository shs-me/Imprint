from abc import ABC
from math import sqrt
from multiprocessing.synchronize import Event

import numpy as np
from numba import njit
from numpy.typing import NDArray

from .... import AgentManager
from ....settings import BarHeaders as bh
from ....settings import SpaceCoords as sc
from ....settings import StateFlags as sf
from .. import ConvertMetrics


class FootprintReader(ABC):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        self.manager, self.send_signal = manager, execution_event
        self.set_status = manager.set_status
        # Footprint
        self.last_idx = 0
        self.cfgFootprint = self.manager.cfgFootprint
        self.space_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.flag : self.cfgFootprint.flag + 1
        ]
        self.spare_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.spare_flag : self.cfgFootprint.spare_flag + 1
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
        self.headers: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.Bar_count, bh._HeadersCount),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.headers)],
        )
        #  - - -
        self.space: NDArray[np.int64] = np.ndarray(
            (2, sc._CoordsCount),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.space)],
        )

    def init_session(self) -> None:
        nBasePrice, baseTimestamp = self.base_price_and_timestamp_buf[:]
        self.con: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par,
            footprint=self.footprint,
            headers=self.headers,
            cfgFootprint=self.cfgFootprint,
        )
        self.con.init_session(price=nBasePrice, timestamp=baseTimestamp)

    def check_update(self) -> None:
        self._update_state()

    def _update_state(self):
        old_flag: int = 1 if self.space_flag[0] == 0 else 0
        IDYmin, IDXmin, IDYmax, IDXmax = self.space[old_flag, :]
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
                self._update_footprint_static_state()
                self.last_idx = idx
        # - - -
        # reset
        self.space[:, sc.IDYmin] = self.con.lines
        self.space[:, sc.IDXmin] = self.con.footprintCols
        self.space[:, sc.IDYmax :] = 0
        self.spare_flag[0] = 0

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
        indicators = sf.BIG_TRADE
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
        indicators = sf.ZERO_PRINT | sf.DELTA_DOMINATION | sf.IMBALANCE
        clear_mask = ~(indicators)

        self.footprint_state[IDYmin : IDYmax + 1, idxBid : idxBid + 2] &= clear_mask

    def _update_zero_print(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        fp_state[idyBid, idxBid][
            ((fp[idyAsk, idxAsk] > 0) & (fp[idyBid, idxBid] == 0))
        ] |= sf.ZERO_PRINT

        fp_state[idyAsk, idxAsk][
            ((fp[idyBid, idxBid] > 0) & (fp[idyAsk, idxAsk] == 0))
        ] |= sf.ZERO_PRINT

    def _update_delta_domination(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        fp_state[idyBid, idxBid][((fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) < 0)] |= (
            sf.DELTA_DOMINATION
        )

        fp_state[idyAsk, idxAsk][((fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) > 0)] |= (
            sf.DELTA_DOMINATION
        )

    def _update_imbalance(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        fp_state[idyBid, idxBid][(fp[idyBid, idxBid] > (fp[idyAsk, idxAsk] * 3))] |= (
            sf.IMBALANCE
        )

        fp_state[idyAsk, idxAsk][(fp[idyAsk, idxAsk] > (fp[idyBid, idxBid] * 3))] |= (
            sf.IMBALANCE
        )

    # - - Bar  - -
    def _update_bar_state(
        self, IDYmin: int, IDYmax: int, idxBid: int, idxAsk: int
    ) -> None:
        open, close = self.con.openPrice(idxBid), self.con.closePrice(idxBid)
        high, low = self.con.highPrice(idxBid), self.con.lowPrice(idxBid)

        self._clear_bar_state(high=high, low=low, idxBid=idxBid)
        self._update_ohlc(idxBid=idxBid, open=open, high=high, low=low, close=close)
        self._update_poc_va_bar(high=high, low=low, idxBid=idxBid)

    def _clear_bar_state(self, high: int, low: int, idxBid: int) -> None:
        headers = sf.OPEN | sf.HIGH | sf.LOW | sf.CLOSE
        indicators = sf.POC_BAR | sf.VAL_BAR | sf.VAH_BAR
        clear_mask = ~(headers | indicators)
        self.footprint_state[high : low + 1, idxBid] &= clear_mask

    def _update_ohlc(
        self, open: int, high: int, low: int, close: int, idxBid: int
    ) -> None:
        self.footprint_state[open, idxBid] |= sf.OPEN
        self.footprint_state[high, idxBid] |= sf.HIGH
        self.footprint_state[low, idxBid] |= sf.LOW
        self.footprint_state[close, idxBid] |= sf.CLOSE

    def _update_poc_va_bar(self, high: int, low: int, idxBid: int) -> None:
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        vp_bar = fp[high : low + 1, idxBid] + fp[high : low + 1, idxBid + 1]
        poc = np.argmax(vp_bar)
        VAH, VAL = calc_value_area(vp_slice=vp_bar, center_idx=poc)
        fp_state[high + poc, idxBid] |= sf.POC_BAR
        fp_state[high + VAH, idxBid] |= sf.VAH_BAR
        fp_state[high + VAL, idxBid] |= sf.VAL_BAR

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
        indicators = sf.BID_DELTA_DOMINATION_FP | sf.ASK_DELTA_DOMINATION_FP
        clear_mask = ~(indicators)
        self.footprint_state[IDYmin:IDYmax, idxLevel] &= clear_mask

    def _update_delta_dominations_fp(
        self, IDYmin: int, IDYmax: int, idxLevel: int
    ) -> None:
        fp, fp_state, idxDP = self.footprint, self.footprint_state, self.con.idxDP
        # - - -
        fp_state[IDYmin:IDYmax, idxLevel][(fp[IDYmin:IDYmax, idxDP] < 0)] |= (
            sf.BID_DELTA_DOMINATION_FP
        )
        fp_state[IDYmin:IDYmax, idxLevel][(fp[IDYmin:IDYmax, idxDP] > 0)] |= (
            sf.ASK_DELTA_DOMINATION_FP
        )

    # - - Footprint: Static - -
    def _update_footprint_static_state(self) -> None:
        idxLevel, idxBarrier = self.con.idxVP, self.con.idxDP  # noqa: F841
        # - - -
        lidx = self.last_idx
        high, low = self.con.highPrice(lidx), self.con.lowPrice(lidx)
        self._clear_footprint_static_state(idxLevel=idxLevel)
        self._update_vwap_bb(lidx=lidx, idxLevel=idxLevel)
        self._update_poc_va_fp(idxLevel=idxLevel)
        self._update_auction(high=high, low=low, idx=lidx, idxLevel=idxLevel)

    def _clear_footprint_static_state(self, idxLevel: int) -> None:
        self.footprint_state[:, idxLevel] &= ~(
            sf.VWAP
            | sf.LOWER_BB
            | sf.UPPER_BB
            | sf.POC_BAR
            | sf.VAL_FP
            | sf.VAH_FP
            | sf.UNFINISHED_AUCTION
            | sf.FINISHED_AUCTION
        )

    def _update_vwap_bb(self, lidx: int, idxLevel: int) -> None:
        sum_w, sum_p2w = self.con.vwap_sum_w(lidx), self.con.vwap_sum_p2w(lidx)
        vwap = self.con.vwap_sum_pw(lidx) / sum_w
        std_dev = sqrt(max(0.0, (sum_p2w / sum_w) - (vwap**2)))
        upper_bb, lower_bb = vwap + (2 * std_dev), vwap - (2 * std_dev)
        self.footprint_state[self.con.to_idy(round(vwap)), idxLevel] |= sf.VWAP
        self.footprint_state[self.con.to_idy(round(upper_bb)), idxLevel] |= sf.UPPER_BB
        self.footprint_state[self.con.to_idy(round(lower_bb)), idxLevel] |= sf.LOWER_BB

    def _update_poc_va_fp(self, idxLevel: int) -> None:
        fp, fp_state, idxVP = self.footprint, self.footprint_state, self.con.idxVP
        # - - -
        poc = np.argmax(fp[:, idxVP])
        VAH, VAL = calc_value_area(vp_slice=fp[:, idxVP], center_idx=poc)
        fp_state[poc, idxLevel] |= sf.POC_FP
        fp_state[VAH, idxLevel] |= sf.VAH_FP
        fp_state[VAL, idxLevel] |= sf.VAL_FP

    def _update_auction(self, high: int, low: int, idx: int, idxLevel: int) -> None:
        fp = self.footprint
        # - - -
        self.footprint_state[high, idxLevel] |= (
            sf.FINISHED_AUCTION if fp[high, idx + 1] == 0 else sf.UNFINISHED_AUCTION
        )
        self.footprint_state[low, idxLevel] |= (
            sf.FINISHED_AUCTION if fp[low, idx] == 0 else sf.UNFINISHED_AUCTION
        )


@njit(cache=True)
def calc_value_area(vp_slice: NDArray[np.int64], center_idx) -> tuple[int, int]:
    target_vol, current_vol = np.sum(vp_slice) * 0.70, vp_slice[center_idx]
    up_idx, down_idx, max_len = center_idx - 1, center_idx + 1, len(vp_slice)
    while current_vol < target_vol:
        if 0 <= up_idx and down_idx < max_len:
            vol_up = vp_slice[up_idx] if 0 <= up_idx else 0
            vol_down = vp_slice[down_idx] if down_idx < max_len else 0
            up_idx -= 1 if vol_up > vol_down or vol_up == vol_down else 0
            down_idx += 1 if vol_down > vol_up or vol_down == vol_up else 0
            current_vol += vol_up + vol_down

        else:
            break

    return up_idx + 1, down_idx - 1
