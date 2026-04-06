from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray

from ... import Config, ManagerAgent
from .. import ConvertMetrics


class FootprintReader(ABC):
    """
    Footprint is 2DArray[float64]. Each even col is BID, odd ASK.\
    Each such pair is a time interval cluster, more than one cluster is Footprint.\
    Index ax 0/Lines/Level/IDY is converted price. Index ax 1/Cols/IDX is converted timestamp.\
    """

    def __init__(self, manager: ManagerAgent) -> None:
        __cfg, self.manager = Config.ShmSharing, manager
        self.set_status = manager.set_status

        # Footprint
        _flag: int = __cfg.Footprint.flag
        self.flag_buf: memoryview[int] = self.manager.footprint_buf[_flag : _flag + 1]
        self.lines, self.cols = __cfg.Footprint.lines, __cfg.Footprint.cols
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
        self.footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.lines, self.cols),
            dtype=np.int64,
        )
        self.footprint[:] = 0.0

        self.coord1: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.coord1)
        ].cast("q")
        self.coord2: memoryview[int] = self.manager.footprint_buf[
            slice(*__cfg.Footprint.coord2)
        ].cast("q")

    def init_session(self) -> None:
        self.nBasePrice, self.nBaseTimestamp = self.nBasePrice_and_timestamp_buf[:]
        self.convert: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par,
            nBasePrice=self.nBasePrice,
            nBaseTimestamp=self.nBaseTimestamp,
        )
        self.convert.init_center()

    def _get_cords(self) -> tuple[int, int]:
        old_flag: int = 1 if self.flag_buf[0] == 0 else 0
        coord = self.coord1 if old_flag == 0 else self.coord2
        idy_min, idx_min, idy_max, idx_max, idy, idx = coord[:]
        np.copyto(  # update grid local
            dst=self.footprint[
                idy_min:idy_max,
                idx_min:idx_max,
            ],
            src=self.footprint_shm[
                idy_min:idy_max,
                idx_min:idx_max,
            ],
        )
        coord[0] = self.lines  # default coord idy_min
        coord[1] = self.cols  # default coord idx_min
        coord[2] = 0  # default coord idy_max
        coord[3] = 0  # default coord idx_max
        coord[4] = 0  # default coord idy
        coord[5] = 0  # default coord idx
        return idy, idx

    def _check_update(self) -> None:
        idy, idx = self._get_cords()
        self.check_patterns(idy=idy, idx=idx, footprint=self.footprint)

    @abstractmethod
    def check_patterns(self, idy: int, idx: int, footprint: NDArray[np.int64]) -> None:
        pass


class BaseFootprintReader(FootprintReader):
    def check_patterns(self, idy: int, idx: int, footprint: NDArray[np.int64]) -> None:
        convert = self.convert
        get_nPice = convert.get_nPrice
        to_price, to_qty = convert.to_price, convert.to_qty
        # - - -
        price, qty = to_price(get_nPice(idy)), to_qty(footprint[idy, idx])
        print(price, qty)
