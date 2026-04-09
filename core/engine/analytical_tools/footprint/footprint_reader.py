from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray

from .... import AgentManager
from ....settings import SpaceCoords as spc
from .. import ConvertMetrics


class FootprintReader(ABC):
    """
    Footprint is 2DArray[int64]. Each even col is BID, odd ASK.\
    Each such pair is a time interval cluster, more than one cluster is Footprint.\
    Index ax 0/Lines/Level/IDY is converted price. Index ax 1/Cols/IDX is converted timestamp.\
    """

    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager
        self.set_status = manager.set_status
        # Footprint
        self.cfgFootprint = self.manager.cfgFootprint
        self.idxVP = self.cfgFootprint.colVP
        self.idxBidVP = self.cfgFootprint.colBidVP
        self.idxAskVP = self.cfgFootprint.colAskVP
        self.lines = self.cfgFootprint.lines
        self.footprintCols = self.cfgFootprint.footprintCols
        self.panelCols = self.cfgFootprint.panelCols
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
            shape=(self.lines, self.panelCols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint)],
        )
        self.footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.lines, self.panelCols),
            dtype=np.int64,
        )
        self.footprint[:] = 0.0

        self.headers_buf: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.headers)
        ].cast("q")

        self.space_1: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_1)
        ].cast("q")
        self.space_2: memoryview[int] = self.manager.footprint_buf[
            slice(*self.cfgFootprint.space_2)
        ].cast("q")

    def init_session(self) -> None:
        nBasePrice, baseTimestamp = self.base_price_and_timestamp_buf[:]
        self.convert: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par, cfgFootprint=self.cfgFootprint
        )
        self.convert.init_session(price=nBasePrice, timestamp=baseTimestamp)

    def _get_cords(self) -> tuple[int, int]:
        old_flag: int = 1 if self.flag_buf[0] == 0 else 0
        space = self.space_1 if old_flag == 0 else self.space_2
        np.copyto(  # update footprint
            dst=self.footprint[
                space[spc.IDYmin] : space[spc.IDYmax],
                space[spc.IDXmin] : space[spc.IDXmax],
            ],
            src=self.footprint_shm[
                space[spc.IDYmin] : space[spc.IDYmax],
                space[spc.IDXmin] : space[spc.IDXmax],
            ],
        )
        np.copyto(  # update indicators
            dst=self.footprint[space[spc.IDYmin] : space[spc.IDYmax], self.idxVP :],
            src=self.footprint_shm[space[spc.IDYmin] : space[spc.IDYmax], self.idxVP :],
        )
        idy, idx = space[spc.IDY], space[spc.IDX]
        # reset
        space[spc.IDYmin], space[spc.IDXmin] = self.lines, self.footprintCols
        space[spc.IDYmax], space[spc.IDXmax] = 0, 0
        space[spc.IDY], space[spc.IDX] = 0, 0
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
        idxVP, idxBidVP, idxAskVP = self.idxVP, self.idxBidVP, self.idxAskVP  # noqa
        convert = self.convert
        get_nPice = convert.get_nPrice
        to_price, to_qty = convert.to_price, convert.to_qty
        # - - -
        price, qty = to_price(get_nPice(idy)), to_qty(footprint[idy, idx])
        vp = to_qty(footprint[idy, idxVP:])
        temp = {"price": price, "qty": qty, "vp_s": vp}
        print(temp, flush=True)
