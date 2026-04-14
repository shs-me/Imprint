from abc import ABC

import numpy as np
from numpy.typing import NDArray

from .... import AgentManager
from ....settings import BarHeaders as chs  # noqa: F401
from ....settings import SpaceCoords as spc
from ....settings import StateFlags as stf
from .. import ConvertMetrics, HeadersGet


class FootprintReader(ABC):
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager
        self.set_status = manager.set_status
        # Footprint
        self.last_box = 0
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
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint_2)],
        )
        self.footprint_state: NDArray[np.int32] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int32,
        )
        self.footprint_state[:] = 0.0
        #  - - -
        self.headers: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.headers_2)
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

    def _update_state(self):
        old_flag: int = 1 if self.flag_buf[0] == 0 else 0
        self.last_box = self.flag_buf[0]
        space = self.space_1 if old_flag == 0 else self.space_2
        IDYmin, IDXmin = space[spc.IDYmin], space[spc.IDXmin]
        IDYmax, IDXmax = space[spc.IDYmax], space[spc.IDXmax]
        for idx in range((IDXmin if IDXmin % 2 == 0 else IDXmin - 1), IDXmax, 2):
            idxBid, idxAsk = idx, idx + 1
            self._update_cluster(
                IDYmin=IDYmin, IDYmax=IDYmax, IDXmin=IDXmin, IDXmax=IDXmax
            )
            self._update_bid_ask_state(
                IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
            )
            self._update_bar_state(
                IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
            )
            self._update_footprint_state(IDYmin=IDYmin, IDYmax=IDYmax)

        # - - -
        # reset
        space[spc.IDYmin], space[spc.IDXmin] = self.con.lines, self.con.footprintCols
        space[spc.IDYmax], space[spc.IDXmax] = 0, 0

    # - - Cluster - -
    def _update_cluster(self, IDYmin: int, IDYmax: int, IDXmin: int, IDXmax: int):
        self._clear_cluster_state(
            IDYmin=IDYmin, IDYmax=IDYmax, IDXmin=IDXmin, IDXmax=IDXmax
        )

    def _clear_cluster_state(self, IDYmin: int, IDYmax: int, IDXmin: int, IDXmax: int):
        indicators = stf.BIG_TRADE
        clear_mask = ~(indicators)
        self.footprint_state[IDYmin:IDYmax, IDXmin:IDXmax] &= clear_mask

    # - - BidAsk  - - -
    def _update_bid_ask_state(self, IDYmin: int, IDYmax: int, idxBid: int, idxAsk: int):
        self._clear_bid_ask_state(IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid)

        self._update_imbalance(
            IDYmin=IDYmin, IDYmax=IDYmax, idxBid=idxBid, idxAsk=idxAsk
        )

    def _clear_bid_ask_state(self, IDYmin: int, IDYmax: int, idxBid: int):
        indicators = stf.ZERO_PRINT | stf.DELTA_DOMINATION | stf.IMBALANCE
        clear_mask = ~(indicators)
        self.footprint_state[IDYmin:IDYmax, idxBid : idxBid + 2] &= clear_mask

    def _update_imbalance(self, IDYmin: int, IDYmax: int, idxBid: int, idxAsk: int):
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        bids = fp[IDYmin + 1 : IDYmax + 1, idxBid]
        asks = fp[IDYmin:IDYmax, idxAsk]

        fp_state[IDYmin + 1 : IDYmax + 1, idxBid][((asks > 0) & (bids == 0))] |= (
            stf.ZERO_PRINT
        )
        fp_state[IDYmin:IDYmax, idxAsk][((bids > 0) & (asks == 0))] |= stf.ZERO_PRINT

        fp_state[IDYmin + 1 : IDYmax + 1, idxBid][((bids - asks) < 0)] |= (
            stf.DELTA_DOMINATION
        )
        fp_state[IDYmin:IDYmax, idxAsk][((bids - asks) > 0)] |= stf.DELTA_DOMINATION

        fp_state[IDYmin + 1 : IDYmax + 1, idxBid][(bids > (asks * 3))] |= stf.IMBALANCE
        fp_state[IDYmin:IDYmax, idxAsk][(asks > (bids * 3))] |= stf.IMBALANCE

    # - - Bar  - -
    def _update_bar_state(self, IDYmin: int, IDYmax: int, idxBid: int, idxAsk: int):
        ind = self.ind
        #  - - -
        open, close = ind.openPrice(idxBid), ind.closePrice(idxBid)
        high, low = ind.highPrice(idxBid), ind.lowPrice(idxBid)

        self._clear_bar_state(high=high, low=low, idxBid=idxBid)

        self._update_ohlc(idxBid=idxBid, open=open, high=high, low=low, close=close)

    def _clear_bar_state(self, high: int, low: int, idxBid: int):
        headers = stf.OPEN | stf.HIGH | stf.LOW | stf.CLOSE
        indicators = stf.POC_BAR | stf.VA_MIN_BAR | stf.VA_MAX_BAR
        clear_mask = ~(headers | indicators)
        self.footprint_state[high : low + 1, idxBid] &= clear_mask

    def _update_ohlc(self, idxBid: int, open: int, high: int, low: int, close: int):
        self.footprint_state[open, idxBid] |= stf.OPEN
        self.footprint_state[high, idxBid] |= stf.HIGH
        self.footprint_state[low, idxBid] |= stf.LOW
        self.footprint_state[close, idxBid] |= stf.CLOSE

    def _update_poc_va_bar(self, high: int, low: int, idxBid: int):
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        vp_bar = fp[high : low + 1, idxBid] + fp[high : low + 1, idxBid + 1]
        poc = np.argmax(vp_bar)
        fp_state[poc, idxBid] |= stf.POC_BAR

    # - - Footprint - -
    def _update_footprint_state(self, IDYmin: int, IDYmax: int):
        idxVP = self.con.idxVP
        # - - -
        pass
        self._clear_footprint_state(idxVP=idxVP)

    def _clear_footprint_state(self, idxVP: int):
        indicators = stf.POC_BAR | stf.VA_MIN_FP | stf.VA_MAX_FP
        clear_mask = ~(indicators)
        self.footprint_state[:, idxVP] &= clear_mask

    def _update_poc_va_fp(self, idxVP: int):
        fp, fp_state = self.footprint, self.footprint_state
        # - - -
        poc = np.argmax(fp[:, idxVP])
        fp_state[poc,] |= stf.POC_BAR
