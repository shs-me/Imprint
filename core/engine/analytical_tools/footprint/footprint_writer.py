from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from .... import AgentManager
from .... import StatusCodes as sc
from ....settings import BarHeaders as chs
from ....settings import SpaceCoords as spc
from .. import ConvertMetrics


class FootprintWriter:
    def __init__(self, manager: AgentManager, guarantee: Event) -> None:
        self.manager, self.guarantee = manager, guarantee
        self.set_status = manager.set_status
        # Footprint
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
        self.footprint_1: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint_1)],
        )
        self.footprint_2: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint_2)],
        )
        # - - -
        self.headers_1: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.headers_1)
        ].cast("q")
        self.headers_2: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.headers_2)
        ].cast("q")
        # - - -
        self.space_1: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_1)
        ].cast("q")
        self.space_2: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_2)
        ].cast("q")

    def init_session(self, price: float, timestamp: int) -> bool:
        bpat = self.base_price_and_timestamp_buf
        # - - -
        self.con: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par,
            footprint=self.footprint_1,
            headers_buf=self.headers_1,
            cfgFootprint=self.cfgFootprint,
        )
        if bpat[0] != 0:
            price, timestamp = bpat[:]
        else:
            self.space_1[spc.IDYmin] = self.space_2[spc.IDYmin] = self.con.lines
            self.space_1[spc.IDXmin] = self.space_2[spc.IDXmin] = self.con.footprintCols
            self.space_1[spc.IDYmax] = self.space_2[spc.IDYmax] = 0
            self.space_1[spc.IDXmax] = self.space_2[spc.IDXmax] = 0

        if self.con.init_session(price, timestamp) is False:
            self.set_status(code=sc.WARN2)
            return False

        bpat[0], bpat[1] = self.con.nBasePrice, self.con.baseTimestamp
        return True

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        con = self.con
        nPrice, nQty = con.to_nPrice(price), con.to_nQty(qty)
        idy: int | None = con.to_idy(nPrice=nPrice)
        idx: int | None = con.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.footprint_1[idy, idx] += nQty
                self._update_headers(
                    idy=idy,
                    idx=idx,
                    nPrice=nPrice,
                    nQty=nQty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                )
                self._update_coords(idy, idx)
                return True

            else:
                self.set_status(code=sc.WARN4)
        else:
            self.set_status(code=sc.WARN3)

        return False

    def _update_headers(
        self, idy: int, idx: int, nPrice: int, nQty: int, timestamp: int, is_sell: bool
    ) -> None:
        hr = self.headers_1
        # - - -
        cid = self.con.get_Bar_id(idx) * chs._HeadersCount
        if hr[cid + chs.CountTrade] == 0:
            hr[cid + chs.Open] = nPrice
            hr[cid + chs.Time] = timestamp
            hr[cid + chs.Low] = nPrice

        if nPrice > hr[cid + chs.High]:
            hr[cid + chs.High] = nPrice

        if nPrice < hr[cid + chs.Low]:
            hr[cid + chs.Low] = nPrice

        hr[cid + chs.Close] = nPrice
        hr[cid + chs.Volume] += nQty
        hr[cid + chs.Delta] += -nQty if is_sell else nQty
        hr[cid + chs.CountTrade] += 1
        self._update_indicators(cid=cid, idy=idy, idx=idx, nPrice=nPrice, nQty=nQty)

    def _update_indicators(
        self, cid: int | np.intp, idy: int, idx: int, nPrice: int, nQty: int
    ) -> None:
        hr, footprint = self.headers_1, self.footprint_1
        # - - -
        if cid == 8:
            # CVD
            hr[cid + chs.CVD] = hr[cid + chs.Delta]
            # Vwap settings
            hr[cid + chs.VWAP_PWeights] = nPrice * hr[cid + chs.Volume]
            hr[cid + chs.VWAP_Weights] = hr[cid + chs.Volume]
        else:
            oldCid = cid - chs._HeadersCount
            # CVD
            hr[cid + chs.CVD] = hr[cid + chs.Delta] + hr[oldCid + chs.CVD]
            # Vwap settings
            hr[cid + chs.VWAP_PWeights] = (nPrice * hr[cid + chs.Volume]) + hr[
                oldCid + chs.VWAP_PWeights
            ]
            hr[cid + chs.VWAP_Weights] = (
                hr[cid + chs.Volume] + hr[oldCid + chs.VWAP_Weights]
            )

        # Vwap
        hr[cid + chs.VWAP] = hr[cid + chs.VWAP_PWeights] // hr[cid + chs.VWAP_Weights]
        # VolumeProfile
        footprint[idy, self.con.idxVP] += nQty
        # DeltaProfile
        footprint[idy, self.con.idxVP] += hr[cid + chs.Delta]

    def _update_coords(self, idy: int, idx: int) -> None:
        IDYmin, IDXmin = spc.IDYmin, spc.IDXmin
        IDYmax, IDXmax = spc.IDYmax, spc.IDXmax
        # - - -
        new_flag: int = 1 if (flag := self.flag_buf[0]) == 0 else 0
        space = self.space_1 if flag == 0 else self.space_2
        space[IDYmin] = idy if space[IDYmin] > idy else space[IDYmin]
        space[IDXmin] = idx if space[IDXmin] > idx else space[IDXmin]
        space[IDYmax] = idy + 1 if space[IDYmax] <= idy else space[IDYmax]
        space[IDXmax] = idx + 1 if space[IDXmax] <= idx else space[IDXmax]

        if self.guarantee.is_set() is False:
            self.headers_2[:] = self.headers_1[:]
            np.copyto(
                dst=self.footprint_2[
                    space[IDYmin] : space[IDYmax],
                    space[IDXmin] : space[IDXmax],
                ],
                src=self.footprint_1[
                    space[IDYmin] : space[IDYmax],
                    space[IDXmin] : space[IDXmax],
                ],
            )
            np.copyto(
                dst=self.footprint_2[space[IDYmin] : space[IDYmax], self.con.idxVP :],
                src=self.footprint_1[space[IDYmin] : space[IDYmax], self.con.idxVP :],
            )
            self.flag_buf[0] = new_flag
            self.guarantee.set()
