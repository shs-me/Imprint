from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from .... import AgentManager
from .... import StatusCodes as sc
from ....settings import ClusterHeaders as chs
from ....settings import SpaceCoords as spc
from .. import ConvertMetrics


class FootprintWriter:
    def __init__(self, manager: AgentManager, guarantee: Event) -> None:
        self.manager, self.guarantee = manager, guarantee
        self.set_status = manager.set_status
        # Footprint
        self.cfgFootprint = self.manager.cfgFootprint
        self.lines, self.cols = self.cfgFootprint.lines, self.cfgFootprint.cols
        self.flag_buf: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.flag : self.cfgFootprint.flag + 1
        ]
        self.active_buffer: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.flag_spare : self.cfgFootprint.flag_spare + 1
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
        self.footprint_shm: NDArray[np.int64] = np.ndarray(
            shape=(self.lines, self.cols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint)],
        )

        self.headers_buf: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.headers)
        ].cast("q")

        self.space_1: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_1)
        ].cast("q")
        self.space_2: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_2)
        ].cast("q")

    def init_session(self, price: float, timestamp: int) -> bool:
        bpat = self.base_price_and_timestamp_buf
        # - - -
        self.convert: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par, cfgFootprint=self.cfgFootprint
        )
        if bpat[0] != 0:
            price, timestamp = bpat[:]
        else:
            self.space_1[spc.IDYmin] = self.space_2[spc.IDYmin] = self.lines
            self.space_1[spc.IDXmin] = self.space_2[spc.IDXmin] = self.cols
            self.space_1[spc.IDYmax] = self.space_2[spc.IDYmax] = 0
            self.space_1[spc.IDXmax] = self.space_2[spc.IDXmax] = 0
            self.space_1[spc.IDY] = self.space_2[spc.IDY] = 0
            self.space_1[spc.IDX] = self.space_2[spc.IDX] = 0

        if self.convert.init_session(price, timestamp) is False:
            self.set_status(code=sc.WARN2)
            return False

        bpat[0], bpat[1] = self.convert.nBasePrice, self.convert.baseTimestamp
        return True

    def _update_headers(
        self, idx: int, nPrice: int, nQty: int, timestamp: int, is_sell: bool
    ) -> None:
        hr_buf = self.headers_buf
        # - - -
        cid = self.convert.get_cluster_id(idx)
        if hr_buf[cid + chs.CountTrade] == 0:
            hr_buf[cid + chs.Open] = nPrice
            hr_buf[cid + chs.Time] = timestamp

        if nPrice > hr_buf[cid + chs.High]:
            hr_buf[cid + chs.High] = nPrice

        if nPrice < hr_buf[cid + chs.Low]:
            hr_buf[cid + chs.Low] = nPrice

        hr_buf[cid + chs.Close] = nPrice
        hr_buf[cid + chs.Volume] += nQty
        hr_buf[cid + chs.Delta] += -nQty if is_sell else nQty
        hr_buf[cid + chs.CountTrade] += 1

    def _set_cords(self, idy: int, idx: int) -> None:
        IDYmin, IDXmin = spc.IDYmin, spc.IDXmin
        IDYmax, IDXmax = spc.IDYmax, spc.IDXmax
        # - - -
        new_flag: int = 1 if (flag := self.flag_buf[0]) == 0 else 0
        space = self.space_1 if flag == 0 else self.space_2
        space[IDYmin] = idy if space[IDYmin] > idy else space[IDYmin]
        space[IDXmin] = idx if space[IDXmin] > idx else space[IDXmin]
        space[IDYmax] = idy + 1 if space[IDYmax] <= idy else space[IDYmax]
        space[IDXmax] = idx + 1 if space[IDXmax] <= idx else space[IDXmax]
        space[spc.IDY], space[spc.IDX] = idy, idx

        if self.guarantee.is_set() is False:
            self.flag_buf[0] = new_flag
            self.active_buffer[0] = 1
            self.guarantee.set()

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        convert = self.convert
        nPrice, nQty = convert.to_nPrice(price), convert.to_nQty(qty)
        idy: int | None = convert.get_idy(nPrice=nPrice)
        idx: int | None = convert.get_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.footprint_shm[idy, idx] += nQty
                self._update_headers(
                    idx=idx,
                    nPrice=nPrice,
                    nQty=nQty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                )
                self._set_cords(idy, idx)
                return True

            else:
                self.set_status(code=sc.WARN4)
        else:
            self.set_status(code=sc.WARN3)

        return False
