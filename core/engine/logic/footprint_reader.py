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
        self.crdInt = __cfg.Footprint.CoordsInt
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
        # - - -
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
        nBasePrice, baseTimestamp = self.nBasePrice_and_timestamp_buf[:]
        self.convert: ConvertMetrics = ConvertMetrics(trade_param=self.trade_par)
        self.convert.init_session(price=nBasePrice, timestamp=baseTimestamp)

    def _get_cords(self) -> tuple[int, int]:
        crdInt = self.crdInt
        old_flag: int = 1 if self.flag_buf[0] == 0 else 0
        coord = self.coord1 if old_flag == 0 else self.coord2
        np.copyto(
            dst=self.footprint[
                coord[crdInt.idy_min] : coord[crdInt.idy_max],
                coord[crdInt.idx_min] : coord[crdInt.idx_max],
            ],
            src=self.footprint_shm[
                coord[crdInt.idy_min] : coord[crdInt.idy_max],
                coord[crdInt.idx_min] : coord[crdInt.idx_max],
            ],
        )
        idy, idx = coord[crdInt.idy :]
        # reset
        coord[crdInt.idy_min], coord[crdInt.idx_min] = self.lines, self.cols
        coord[crdInt.idy_max], coord[crdInt.idx_max] = 0, 0
        coord[crdInt.idy], coord[crdInt.idx] = 0, 0
        self.active_buffer[0] = 0
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
