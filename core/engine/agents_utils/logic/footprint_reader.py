from abc import ABC
from multiprocessing.synchronize import Event

import numpy as np
from numba import njit
from numpy import bool_, int32, int64, intp
from numpy.typing import NDArray

from core.engine.agents_utils.utils import FPconverter
from core.settings import BarHeaders as bh
from core.settings import OrderFlag as of
from core.settings import SpaceCoords as sc
from core.settings import StateFlags as sf
from core.utils.monitoring.agent_manager import AgentManager


class FootprintReader(ABC):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        self.manager: AgentManager = manager
        self.execution_event: Event = execution_event

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
        # Strategy
        self.cfgST = self.manager.cfgStrategy
        # L/S Buf Setup
        self.cell_amount: int = self.cfgST.cell_amount
        self.readerId: int = self.cfgST.reader[1] // 8 - 1
        self.writerId: int = self.cfgST.writer[1] // 8 - 1
        self.nPriceId: int = self.cfgST.nPrice[1] // 8 - 1
        self.time_msId: int = self.cfgST.time_ms[1] // 8 - 1
        self.orderParamId: int = self.cfgST.orderParam[1] // 8 - 1
        self.signal_size: int = self.cfgST.signal_size // 8
        self.signal_offset: int = self.cfgST.offset // 8

        self.executeBuf: memoryview = self.manager.strategy_buf[
            slice(*self.cfgST.executeBuf)
        ].cast("q")
        # - - -
        self.con: FPconverter = FPconverter(
            footprint=self.fp,
            headers=self.headers,
            trade_param=self.trade_par,
            cfgFP=self.cfgFP,
        )

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

    def init_session(self) -> None:
        nBasePrice, baseTimestamp = self.base_price_and_timestamp_buf[:]
        self.fp_state.fill(0)
        self.last_idx = 0
        self.con.init_session(price=nBasePrice, timestamp=baseTimestamp)

    # - - Strategy Methods - -
    def send_signal(
        self,
        nPrice: int,
        time_ms: int,
        is_long: bool,
        is_buy: bool,
    ) -> None:
        orderParam = 0

        orderParam |= of.LONG if is_long else of.SHORT
        orderParam |= of.BUY if is_buy else of.SELL

        cell: int = self.executeBuf[self.writerId]
        start: int = cell * self.signal_size + self.signal_offset

        self.executeBuf[start + self.nPriceId] = nPrice
        self.executeBuf[start + self.time_msId] = time_ms
        self.executeBuf[start + self.orderParamId] = orderParam

        new_cell = cell + 1
        self.executeBuf[self.writerId] = new_cell if new_cell < self.cell_amount else 0
        if self.execution_event.is_set() is False:
            self.execution_event.set()

    # - - Footprint Analysis/Update Methods - -
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
        _, _fp, fp_state = self.con, self.fp, self.fp_state
        # - - -
        # Clear State's
        fp_state[IDYmin:IDYmax, IDXmin:IDXmax] &= ~(sf.BIG_TRADE)

    # - - BidAsk  - - -
    def _update_bid_ask_state(
        self, IDYmin: int64, IDYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        _, fp, fp_state = self.con, self.fp, self.fp_state
        # - - -
        idyBid: slice[int64, int64] = slice(IDYmin + 1, IDYmax + 1)
        idyAsk: slice[int64, int64] = slice(IDYmin, IDYmax)
        # Clear State's
        indicators = sf.ZERO_PRINT | sf.DELTA_DOMINATION | sf.IMBALANCE
        clear_mask = ~(indicators)
        fp_state[IDYmin : IDYmax + 1, idxBid : idxBid + 2] &= clear_mask
        # Update ZeroPrint
        bidZP: NDArray[bool_] = (fp[idyAsk, idxAsk] > 0) & (fp[idyBid, idxBid] == 0)
        askZP: NDArray[bool_] = (fp[idyBid, idxBid] > 0) & (fp[idyAsk, idxAsk] == 0)
        fp_state[idyBid, idxBid][bidZP] |= sf.ZERO_PRINT
        fp_state[idyAsk, idxAsk][askZP] |= sf.ZERO_PRINT
        # Update Delta Domination
        bidDD: NDArray[bool_] = (fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) < 0
        askDD: NDArray[bool_] = (fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) > 0
        fp_state[idyBid, idxBid][bidDD] |= sf.DELTA_DOMINATION
        fp_state[idyAsk, idxAsk][askDD] |= sf.DELTA_DOMINATION
        # Update IMBALANCE
        bidImb: NDArray[bool_] = fp[idyBid, idxBid] > (fp[idyAsk, idxAsk] * 3)
        askImb: NDArray[bool_] = fp[idyAsk, idxAsk] > (fp[idyBid, idxBid] * 3)
        fp_state[idyBid, idxBid][bidImb] |= sf.IMBALANCE
        fp_state[idyAsk, idxAsk][askImb] |= sf.IMBALANCE

    # - - Bar  - -
    def _update_bar_state(
        self, IDYmin: int64, IDYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        _, fp, fp_state = self.con, self.fp, self.fp_state
        # - - -
        OPEN: int64 = _.to_idy(_.openNprice(idxBid))
        HIGH: int64 = _.to_idy(_.highNprice(idxBid))
        LOW: int64 = _.to_idy(_.lowNprice(idxBid))
        CLOSE: int64 = _.to_idy(_.closeNprice(idxBid))
        # Clear State's
        headers = sf.OPEN | sf.HIGH | sf.LOW | sf.CLOSE
        indicators = sf.POC_BAR | sf.VAL_BAR | sf.VAH_BAR
        clear_mask = ~(headers | indicators)
        fp_state[HIGH : LOW + 1, idxBid] &= clear_mask
        # Update OHLC
        fp_state[OPEN, idxBid] |= sf.OPEN
        fp_state[HIGH, idxBid] |= sf.HIGH
        fp_state[LOW, idxBid] |= sf.LOW
        fp_state[CLOSE, idxBid] |= sf.CLOSE
        # Update VA + POC
        vp_bar: NDArray[int64] = fp[HIGH : LOW + 1, idxBid] + fp[HIGH : LOW + 1, idxAsk]
        poc: intp = np.argmax(vp_bar)
        vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
        fp_state[HIGH + poc, idxBid] |= sf.POC_BAR
        fp_state[HIGH + vah, idxBid] |= sf.VAH_BAR
        fp_state[HIGH + val, idxBid] |= sf.VAL_BAR

    # - - Footprint: RealTime - -
    def _update_fp_realtime_state(self, IDYmin: int64, IDYmax: int64) -> None:
        _, fp, fp_state = self.con, self.fp, self.fp_state
        # - - -
        idxLevel = _.idxVP
        # Clear State's
        indicators = sf.BID_DELTA_DOMINATION_FP | sf.ASK_DELTA_DOMINATION_FP
        clear_mask = ~(indicators)
        fp_state[IDYmin:IDYmax, idxLevel] &= clear_mask
        # Update Delta Domination
        bidDD: NDArray[bool_] = fp[IDYmin:IDYmax, _.idxDP] < 0
        askDD: NDArray[bool_] = fp[IDYmin:IDYmax, _.idxDP] > 0
        fp_state[IDYmin:IDYmax, idxLevel][bidDD] |= sf.BID_DELTA_DOMINATION_FP
        fp_state[IDYmin:IDYmax, idxLevel][askDD] |= sf.ASK_DELTA_DOMINATION_FP

    # - - Footprint: Static - -
    def _update_fp_static_state(self) -> None:
        _, fp, fp_state = self.con, self.fp, self.fp_state
        # - - -
        lidx, idxLevel = self.last_idx, _.idxVP
        HIGH: int64 = _.to_idy(_.highNprice(lidx))
        LOW: int64 = _.to_idy(_.lowNprice(lidx))
        # Clear State's
        state_1 = sf.VWAP | sf.LOWER_BB | sf.UPPER_BB
        state_2 = sf.POC_BAR | sf.VAL_FP | sf.VAH_FP
        state_3 = sf.UNFINISHED_AUCTION | sf.FINISHED_AUCTION
        fp_state[:, idxLevel] &= ~(state_1 | state_2 | state_3)
        # Update VWAP+BB
        vwap: int64 = _.vwap(lidx)
        bb_lower: int64 = _.vwap_bb_lower(lidx)
        bb_upper: int64 = _.vwap_bb_upper(lidx)
        fp_state[_.to_idy(vwap), idxLevel] |= sf.VWAP
        fp_state[_.to_idy(bb_lower), idxLevel] |= sf.LOWER_BB
        fp_state[_.to_idy(bb_upper), idxLevel] |= sf.UPPER_BB
        # Update POC + VA
        poc: intp = np.argmax(fp[:, _.idxVP])
        vah, val = calc_value_area(vp_slice=fp[:, _.idxVP], center_idx=poc)
        fp_state[poc, idxLevel] |= sf.POC_FP
        fp_state[vah, idxLevel] |= sf.VAH_FP
        fp_state[val, idxLevel] |= sf.VAL_FP
        # Update Auction
        highAuction = (
            sf.FINISHED_AUCTION if fp[HIGH, lidx + 1] == 0 else sf.UNFINISHED_AUCTION
        )
        lowAuction = (
            sf.FINISHED_AUCTION if fp[LOW, lidx] == 0 else sf.UNFINISHED_AUCTION
        )
        fp_state[HIGH, idxLevel] |= highAuction
        fp_state[LOW, idxLevel] |= lowAuction


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
