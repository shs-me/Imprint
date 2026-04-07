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
        self.crdInt = __cfg.Footprint.CoordsInt
        self.headersInt = __cfg.Footprint.HeadersInt
        self.lines, self.cols = __cfg.Footprint.lines, __cfg.Footprint.cols
        self.flag_buf: memoryview[int] = self.manager.footprint_buf[
            __cfg.Footprint.flag : __cfg.Footprint.flag + 1
        ]
        self.active_buffer: memoryview[int] = self.manager.footprint_buf[
            __cfg.Footprint.flag_spare : __cfg.Footprint.flag_spare + 1
        ]
        self.nBasePrice_and_timestamp_buf: memoryview[int] = self.manager.footprint_buf[
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

        self.headers: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.headers)
        ].cast("q")

        self.coord1: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.coord1)
        ].cast("q")
        self.coord2: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.coord2)
        ].cast("q")

    def init_session(self, price: float, timestamp: int) -> bool:
        crdInt, coord1, coord2 = self.crdInt, self.coord1, self.coord2
        bpat = self.nBasePrice_and_timestamp_buf
        # - - -
        self.convert: ConvertMetrics = ConvertMetrics(trade_param=self.trade_par)
        if bpat[0] != 0:
            price, timestamp = bpat[:]
        else:
            coord1[crdInt.idy_min] = coord2[crdInt.idy_min] = self.lines
            coord1[crdInt.idx_min] = coord2[crdInt.idx_min] = self.cols
            coord1[crdInt.idy_max] = coord2[crdInt.idy_max] = 0
            coord1[crdInt.idx_max] = coord2[crdInt.idx_max] = 0
            coord1[crdInt.idy] = coord2[crdInt.idy] = 0
            coord1[crdInt.idx] = coord2[crdInt.idx] = 0

        if self.convert.init_session(price, timestamp) is False:
            self.set_status(code=sc.WARN2)
            return False

        bpat[0], bpat[1] = self.convert.nBasePrice, self.convert.baseTimestamp
        return True

    def _update_headers(
        self, idx: int, nPrice: int, nQty: int, timestamp: int, is_sell: bool
    ) -> None:
        hr_buf, hr = self.headers, self.headersInt
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
        idy_min, idx_min = self.crdInt.idy_min, self.crdInt.idx_min
        idy_max, idx_max = self.crdInt.idy_max, self.crdInt.idx_max
        _idy, _idx = self.crdInt.idy, self.crdInt.idx
        # - - -
        new_flag: int = 1 if (flag := self.flag_buf[0]) == 0 else 0
        coord = self.coord1 if flag == 0 else self.coord2
        coord[idy_min] = idy if coord[idy_min] > idy else coord[idy_min]
        coord[idx_min] = idx if coord[idx_min] > idx else coord[idx_min]
        coord[idy_max] = idy + 1 if coord[idy_max] <= idy else coord[idy_max]
        coord[idx_max] = idx + 1 if coord[idx_max] <= idx else coord[idx_max]
        coord[_idy], coord[_idx] = idy, idx

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
