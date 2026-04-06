from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from ... import Config, ManagerAgent
from ... import StatusCodes as sc
from .. import ConvertMetrics


class FootprintWriter:
    def __init__(self, manager: ManagerAgent, guarantee: Event) -> None:
        __cfg, self.manager, self.guarantee = Config.ShmSharing, manager, guarantee
        self.set_status = manager.set_status

        # Footprint
        self.nBasePrice, self.nBaseTimestamp = 0, 0
        _flag: int = __cfg.Footprint.flag
        self.flag_buf: memoryview[int] = self.manager.footprint_buf[_flag : _flag + 1]
        self.headers = __cfg.Footprint.Headers
        self.lines, self.cols = __cfg.Footprint.lines, __cfg.Footprint.cols
        self.nBasePrice_and_Timestamp_buf: memoryview[int] = self.manager.footprint_buf[
            __cfg.Footprint.nBasePrice[0] : __cfg.Footprint.nBaseTimestamp[1]
        ].cast("q")

        # Metrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            __cfg.Metrics.tick_size[0] : __cfg.Metrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self._init_array()

    def _init_array(self) -> None:
        __cfg: type[Config.ShmSharing] = Config.ShmSharing
        self.footprint_shm: NDArray[np.int64] = np.ndarray(
            shape=(self.lines, self.cols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*__cfg.Footprint.footprint)],
        )

        self.headers_buf: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.headers)
        ].cast("q")

        self.coord1_buf: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.coord1)
        ].cast("q")
        self.coord2_buf: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.coord2)
        ].cast("q")

    def init_session(self, price: float, timestamp: int) -> bool:
        self.pricePrec, self.qtyPrec = self.trade_par[2:4]
        self.nBasePrice: int = round(price * (10**self.pricePrec))
        self.nBaseTimestamp: int = timestamp
        self.convert: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par,
            nBasePrice=self.nBasePrice,
            nBaseTimestamp=self.nBaseTimestamp,
        )

        if self.convert.init_center() is False:
            self.set_status(code=sc.WARN2)
            return False

        self.nBasePrice_and_Timestamp_buf[0] = self.nBasePrice
        self.nBasePrice_and_Timestamp_buf[1] = self.nBaseTimestamp
        self.coord1_buf[0] = self.coord2_buf[0] = self.lines  # default coord idy_min
        self.coord1_buf[1] = self.coord2_buf[1] = self.cols  # default coord idx_min
        self.coord1_buf[2] = self.coord2_buf[2] = 0  # default coord idy_max
        self.coord1_buf[3] = self.coord2_buf[3] = 0  # default coord idx_max
        self.coord1_buf[4] = self.coord2_buf[4] = 0  # default coord idy
        self.coord1_buf[5] = self.coord2_buf[5] = 0  # default coord idx
        return True

    def _update_headers(
        self, idx: int, nPrice: int, nQty: int, timestamp: int, is_sell: bool
    ) -> None:
        hr_buf, hr = self.headers_buf, self.headers
        # - - -
        cid = self.convert.get_cluster_id(idx)
        if hr_buf[cid + hr.CountTrade] == 0:
            hr_buf[cid + hr.Open] = nPrice
            hr_buf[cid + hr.Time] = timestamp

        if nPrice > hr_buf[cid + hr.High]:
            hr_buf[cid + hr.High] = nPrice

        if nPrice < hr_buf[cid + hr.Low]:
            hr_buf[cid + hr.Low] = nPrice

        hr_buf[cid + hr.Close] = nPrice
        hr_buf[cid + hr.Volume] += nQty
        hr_buf[cid + hr.Delta] += -nQty if is_sell else nQty
        hr_buf[cid + hr.CountTrade] += 1

    def _set_cords(self, idy: int, idx: int) -> None:
        new_flag: int = 1 if (flag := self.flag_buf[0]) == 0 else 0
        coord = self.coord1_buf if flag == 0 else self.coord2_buf
        coord[0] = idy if coord[0] > idy else coord[0]  # idy_min
        coord[1] = idx if coord[1] > idx else coord[1]  # idx_min
        coord[2] = idy + 1 if coord[2] <= idy else coord[2]  # idy_max
        coord[3] = idx + 1 if coord[3] <= idx else coord[3]  # idx_max
        coord[4] = idy
        coord[5] = idx
        if self.guarantee.is_set() is False:
            self.flag_buf[0] = new_flag
            self.guarantee.set()

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        convert = self.convert
        nPrice, nQty = convert.to_nPrice(price), convert.to_nQty(qty)
        idy: int | None = convert.get_idy(nPrice=nPrice)
        idx: int | None = convert.get_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.footprint_shm[idy, idx] += nQty  # update bid|ask
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
