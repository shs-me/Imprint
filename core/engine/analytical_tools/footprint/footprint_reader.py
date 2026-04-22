from abc import ABC
from multiprocessing.synchronize import Event

import numpy as np
from numba import njit
from numpy import bool_, int32, int64, intp
from numpy.typing import NDArray

from .... import AgentManager
from ....settings import BarHeaders as bh
from ....settings import SpaceCoords as sc
from ....settings import StateFlags as sf
from .. import ConvertMetrics


class FootprintReader(ABC):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        self.manager, self.execution_event = manager, execution_event
        self.set_status = manager.set_status
        # Variable's
        self.last_idx: int = 0
        # Footprint
        self.cfgFP = self.manager.cfgFootprint
        self.space_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFP.flag : self.cfgFP.flag + 1
        ]
        self.spare_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFP.spare_flag : self.cfgFP.spare_flag + 1
        ]
        self.base_price_and_timestamp_buf: memoryview[int] = self.manager.footprint_buf[
            self.cfgFP.basePrice[0] : self.cfgFP.baseTimestamp[1]
        ].cast("q")
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self._init_array()

    def _init_array(self) -> None:
        self.fp: NDArray[int64] = np.ndarray(
            shape=(self.cfgFP.fpLines, self.cfgFP.fpPanelCols),
            dtype=int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFP.footprint)],
        )
        self.fp_state: NDArray[int32] = np.ndarray(
            shape=(self.cfgFP.fpLines, self.cfgFP.fpPanelCols),
            dtype=int32,
        )
        self.fp_state.fill(0)
        #  - - -
        self.headers: NDArray[int64] = np.ndarray(
            shape=(self.cfgFP.bar_count, bh._HeadersCount),
            dtype=int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFP.headers)],
        )
        #  - - -
        self.space: NDArray[int64] = np.ndarray(
            (2, sc._CoordsCount),
            dtype=int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFP.space)],
        )

    def _save_array(self) -> None:
        np.save("footprint", self.fp)
        np.save("headers", self.headers)

    def init_session(self) -> None:
        nBasePrice, baseTimestamp = self.base_price_and_timestamp_buf[:]
        self.con: ConvertMetrics = ConvertMetrics(
            footprint=self.fp,
            headers=self.headers,
            trade_param=self.trade_par,
            cfgFP=self.cfgFP,
        )
        self.con.init_session(price=nBasePrice, timestamp=baseTimestamp)

    def check_update(self) -> None:
        self._update_state()

    def _update_state(self):
        IDYmin: int64
        IDXmin: int64
        IDYmax: int64
        IDXmax: int64

        oldBuf: int = 1 if self.space_flag[0] == 0 else 0
        IDYmin, IDXmin, IDYmax, IDXmax = self.space[oldBuf, :]

        self._update_cluster(IDYmin=IDYmin, IDYmax=IDYmax, IDXmin=IDXmin, IDXmax=IDXmax)
        self._update_fp_realtime_state(IDYmin=IDYmin, IDYmax=IDYmax)
        for idx in range((IDXmin & ~1), IDXmax, 2):
            idxBid, idxAsk = idx, idx + 1
            self._update_bid_ask_state(
                IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
            )
            self._update_bar_state(
                IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
            )
            if idx > self.last_idx:
                self._update_fp_static_state()
                self.last_idx = idx

        self.space[oldBuf, :] = self.con.fpLines, self.con.fpCols, 0, 0

    # - - Cluster - -
    def _update_cluster(
        self, IDYmin: int64, IDYmax: int64, IDXmin: int64, IDXmax: int64
    ) -> None:
        self._clear_cluster_state(
            IDYmin=IDYmin, IDYmax=IDYmax, IDXmin=IDXmin, IDXmax=IDXmax
        )

    def _clear_cluster_state(
        self, IDYmin: int64, IDYmax: int64, IDXmin: int64, IDXmax: int64
    ) -> None:
        self.fp_state[IDYmin:IDYmax, IDXmin:IDXmax] &= ~(sf.BIG_TRADE)

    # - - BidAsk  - - -
    def _update_bid_ask_state(
        self, IDYmin: int64, IDYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        idyBid: slice[int64, int64] = slice(IDYmin + 1, IDYmax + 1)
        idyAsk: slice[int64, int64] = slice(IDYmin, IDYmax)
        self._clear_bid_ask_state(IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid)
        self._update_zero_print(
            idyBid=idyBid, idyAsk=idyAsk, idxBid=idxBid, idxAsk=idxAsk
        )
        self._update_delta_domination(
            idyBid=idyBid, idyAsk=idyAsk, idxBid=idxBid, idxAsk=idxAsk
        )
        self._update_imbalance(
            idyBid=idyBid, idyAsk=idyAsk, idxBid=idxBid, idxAsk=idxAsk
        )

    def _clear_bid_ask_state(self, IDYmin: int64, IDYmax: int64, idxBid: int) -> None:
        indicators = sf.ZERO_PRINT | sf.DELTA_DOMINATION | sf.IMBALANCE
        clear_mask = ~(indicators)

        self.fp_state[IDYmin : IDYmax + 1, idxBid : idxBid + 2] &= clear_mask

    def _update_zero_print(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        bidZP: NDArray[bool_] = (self.fp[idyAsk, idxAsk] > 0) & (
            self.fp[idyBid, idxBid] == 0
        )
        askZP: NDArray[bool_] = (self.fp[idyBid, idxBid] > 0) & (
            self.fp[idyAsk, idxAsk] == 0
        )
        self.fp_state[idyBid, idxBid][bidZP] |= sf.ZERO_PRINT
        self.fp_state[idyAsk, idxAsk][askZP] |= sf.ZERO_PRINT

    def _update_delta_domination(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        bidDD: NDArray[bool_] = (self.fp[idyBid, idxBid] - self.fp[idyAsk, idxAsk]) < 0
        askDD: NDArray[bool_] = (self.fp[idyBid, idxBid] - self.fp[idyAsk, idxAsk]) > 0
        self.fp_state[idyBid, idxBid][bidDD] |= sf.DELTA_DOMINATION
        self.fp_state[idyAsk, idxAsk][askDD] |= sf.DELTA_DOMINATION

    def _update_imbalance(
        self, idyBid: slice, idyAsk: slice, idxBid: int, idxAsk: int
    ) -> None:
        bidImb: NDArray[bool_] = self.fp[idyBid, idxBid] > (self.fp[idyAsk, idxAsk] * 3)
        askImb: NDArray[bool_] = self.fp[idyAsk, idxAsk] > (self.fp[idyBid, idxBid] * 3)
        self.fp_state[idyBid, idxBid][bidImb] |= sf.IMBALANCE
        self.fp_state[idyAsk, idxAsk][askImb] |= sf.IMBALANCE

    # - - Bar  - -
    def _update_bar_state(
        self, IDYmin: int64, IDYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        _ = self.con

        OPEN: int64 = _.openIdy(idxBid)
        HIGH: int64 = _.highIdy(idxBid)
        LOW: int64 = _.lowIdy(idxBid)
        CLOSE: int64 = _.closeIdy(idxBid)

        self._clear_bar_state(HIGH=HIGH, LOW=LOW, idxBid=idxBid)
        self._update_ohlc(idxBid=idxBid, OPEN=OPEN, HIGH=HIGH, LOW=LOW, CLOSE=CLOSE)
        self._update_poc_va_bar(HIGH=HIGH, LOW=LOW, idxBid=idxBid, idxAsk=idxAsk)

    def _clear_bar_state(self, HIGH: int64, LOW: int64, idxBid: int) -> None:
        headers = sf.OPEN | sf.HIGH | sf.LOW | sf.CLOSE
        indicators = sf.POC_BAR | sf.VAL_BAR | sf.VAH_BAR
        clear_mask = ~(headers | indicators)
        self.fp_state[HIGH : LOW + 1, idxBid] &= clear_mask

    def _update_ohlc(
        self, OPEN: int64, HIGH: int64, LOW: int64, CLOSE: int64, idxBid: int
    ) -> None:
        self.fp_state[OPEN, idxBid] |= sf.OPEN
        self.fp_state[HIGH, idxBid] |= sf.HIGH
        self.fp_state[LOW, idxBid] |= sf.LOW
        self.fp_state[CLOSE, idxBid] |= sf.CLOSE

    def _update_poc_va_bar(
        self, HIGH: int64, LOW: int64, idxBid: int, idxAsk: int
    ) -> None:
        vp_bar: NDArray[int64] = (
            self.fp[HIGH : LOW + 1, idxBid] + self.fp[HIGH : LOW + 1, idxAsk]
        )
        poc: intp = np.argmax(vp_bar)
        vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
        self.fp_state[HIGH + poc, idxBid] |= sf.POC_BAR
        self.fp_state[HIGH + vah, idxBid] |= sf.VAH_BAR
        self.fp_state[HIGH + val, idxBid] |= sf.VAL_BAR

    # - - Footprint: RealTime - -
    def _update_fp_realtime_state(self, IDYmin: int64, IDYmax: int64) -> None:
        idxLevel = self.con.idxVP
        self._clear_fp_realtime_state(IDYmin=IDYmin, IDYmax=IDYmax, idxLevel=idxLevel)
        self._update_delta_dominations_fp(
            IDYmin=IDYmin, IDYmax=IDYmax, idxLevel=idxLevel
        )

    def _clear_fp_realtime_state(
        self, IDYmin: int64, IDYmax: int64, idxLevel: int
    ) -> None:
        indicators = sf.BID_DELTA_DOMINATION_FP | sf.ASK_DELTA_DOMINATION_FP
        clear_mask = ~(indicators)
        self.fp_state[IDYmin:IDYmax, idxLevel] &= clear_mask

    def _update_delta_dominations_fp(
        self, IDYmin: int64, IDYmax: int64, idxLevel: int
    ) -> None:
        bidDD: NDArray[bool_] = self.fp[IDYmin:IDYmax, self.con.idxDP] < 0
        askDD: NDArray[bool_] = self.fp[IDYmin:IDYmax, self.con.idxDP] > 0
        self.fp_state[IDYmin:IDYmax, idxLevel][bidDD] |= sf.BID_DELTA_DOMINATION_FP
        self.fp_state[IDYmin:IDYmax, idxLevel][askDD] |= sf.ASK_DELTA_DOMINATION_FP

    # - - Footprint: Static - -
    def _update_fp_static_state(self) -> None:
        lidx, idxLevel, idxBarrier = self.last_idx, self.con.idxVP, self.con.idxDP
        HIGH, LOW = self.con.highIdy(lidx), self.con.lowIdy(lidx)
        self._clear_fp_static_state(idxLevel=idxLevel)
        self._update_vwap_bb(lidx=lidx, idxLevel=idxLevel)
        self._update_poc_va_fp(idxLevel=idxLevel)
        self._update_auction(HIGH=HIGH, LOW=LOW, idx=lidx, idxLevel=idxLevel)

    def _clear_fp_static_state(self, idxLevel: int) -> None:
        state_1 = sf.VWAP | sf.LOWER_BB | sf.UPPER_BB
        state_2 = sf.POC_BAR | sf.VAL_FP | sf.VAH_FP
        state_3 = sf.UNFINISHED_AUCTION | sf.FINISHED_AUCTION
        self.fp_state[:, idxLevel] &= ~(state_1 | state_2 | state_3)

    def _update_vwap_bb(self, lidx: int, idxLevel: int) -> None:
        _ = self.con
        vwap: int64 = _.vwap(lidx)
        bb_lower: int64 = _.vwap_bb_lower(lidx)
        bb_upper: int64 = _.vwap_bb_upper(lidx)
        self.fp_state[_.to_idy(vwap), idxLevel] |= sf.VWAP
        self.fp_state[_.to_idy(bb_lower), idxLevel] |= sf.LOWER_BB
        self.fp_state[_.to_idy(bb_upper), idxLevel] |= sf.UPPER_BB

    def _update_poc_va_fp(self, idxLevel: int) -> None:
        poc: intp = np.argmax(self.fp[:, self.con.idxVP])
        vah, val = calc_value_area(vp_slice=self.fp[:, self.con.idxVP], center_idx=poc)
        self.fp_state[poc, idxLevel] |= sf.POC_FP
        self.fp_state[vah, idxLevel] |= sf.VAH_FP
        self.fp_state[val, idxLevel] |= sf.VAL_FP

    def _update_auction(self, HIGH: int64, LOW: int64, idx: int, idxLevel: int) -> None:
        highAuction = (
            sf.FINISHED_AUCTION
            if self.fp[HIGH, idx + 1] == 0
            else sf.UNFINISHED_AUCTION
        )
        lowAuction = (
            sf.FINISHED_AUCTION if self.fp[LOW, idx] == 0 else sf.UNFINISHED_AUCTION
        )
        self.fp_state[HIGH, idxLevel] |= highAuction
        self.fp_state[LOW, idxLevel] |= lowAuction


@njit(cache=True)
def calc_value_area(vp_slice: NDArray[int64], center_idx: intp) -> tuple[intp, intp]:
    target_vol: float = np.sum(vp_slice) * 0.70
    current_vol: int64 = vp_slice[center_idx]
    max_len: int = len(vp_slice)
    up_idx: intp = center_idx - 1
    down_idx: intp = center_idx + 1
    while current_vol < target_vol:
        if 0 <= up_idx or down_idx < max_len:
            vol_up = vp_slice[up_idx] if 0 <= up_idx else 0
            vol_down = vp_slice[down_idx] if down_idx < max_len else 0
            up_idx -= 1 if vol_up > vol_down or vol_up == vol_down else 0
            down_idx += 1 if vol_down > vol_up or vol_down == vol_up else 0
            current_vol += vol_up + vol_down

        else:
            break

    return up_idx + 1, down_idx - 1
