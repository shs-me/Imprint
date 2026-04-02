import traceback
from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray

from ... import Config, MonitorObj
from .. import ConvertMetrics


class GridReader(ABC):
    """
    Footprint is 2DArray[float64]. Each even col is BID, odd ASK.\
    Each such pair is a time interval cluster, more than one cluster is Footprint.\
    Index ax 0/Lines/Level/IDY is converted price. Index ax 1/Cols/IDX is converted timestamp.\
    """

    def __init__(self, mo: MonitorObj) -> None:
        __cfg, self._mo = Config.CoreConfig, mo
        self.id_m = self._mo.id_d
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.lines, self.cols = __cfg.Grid.lines, __cfg.Grid.cols
        self.OHLCV_T_D_CT: list[int] = [
            self.lines + 0,  # Open price
            self.lines + 1,  # High
            self.lines + 2,  # Low
            self.lines + 3,  # Close
            self.lines + 4,  # Volume
            self.lines + 5,  # Timestamp
            self.lines + 6,  # Delta
            self.lines + 7,  # Count Trade
        ]
        self.tick_size, self.base_price, self.base_timestamp = 0.0, 0.0, 0
        self.center, self.ims = 0, Config.UserConfig.interval_min * 60 * 1000
        _flag: int = __cfg.Metrics.flag
        self.flag_buf: memoryview[int] = self._mo.metrics_buf[_flag : _flag + 1]
        self.tick_size_buf: memoryview[float] = self._mo.metrics_buf[
            slice(*__cfg.Metrics.tick_size)
        ].cast("d")
        self.base_price_buf: memoryview[float] = self._mo.metrics_buf[
            slice(*__cfg.Metrics.base_price)
        ].cast("d")
        self.base_timestamp_buf: memoryview[int] = self._mo.metrics_buf[
            slice(*__cfg.Metrics.base_timestamp)
        ].cast("q")

        self._init_array()

    def _init_array(self) -> None:
        try:
            __cfg: type[Config.CoreConfig] = Config.CoreConfig
            self.footprint: NDArray[np.float64] = np.ndarray(
                shape=((self.lines + 8), self.cols),
                dtype=np.float64,
            )
            self.footprint[:] = 0.0
            self.grid: NDArray[np.float64] = np.ndarray(
                shape=((self.lines + 8), self.cols),
                dtype=np.float64,
                buffer=self._mo.grid_buf,
            )
            self.coord: NDArray[np.int32] = np.ndarray(
                shape=(
                    __cfg.Metrics.coord_lines,
                    __cfg.Metrics.coord_cols,
                ),
                dtype=np.int32,
                buffer=self._mo.metrics_buf[slice(*__cfg.Metrics.coord_offset)],
            )
        except Exception:
            traceback.print_exc()  # Debug
            self.set_status(id_m=self.id_m, code=150)  # Error in this func

    def _init_session(self) -> None:
        """Get BasePrice, BaseTimestamp, TickSize"""
        self.tick_size: float = self.tick_size_buf[0]
        self.base_price: float = self.base_price_buf[0]
        self.base_timestamp: int = self.base_timestamp_buf[0]

        atip: int = round(  # Amount Ticks In Price
            number=self.base_price / self.tick_size
        )
        self.center: int = atip if atip >= (self.lines - atip) else (self.lines - atip)
        self.convert: ConvertMetrics = ConvertMetrics(
            tick_size=self.tick_size,
            base_price=self.base_price,
            base_timestamp=self.base_timestamp,
            center=self.center,
            lines=self.lines,
            cols=self.cols,
            ims=self.ims,
        )

    def _get_cords(self) -> tuple[int, int]:
        """Get Coordinaties IDY:IDX from 2-D Array 'Cord'"""
        coord = self.coord
        # - - -
        old_flag: int = 1 if self.flag_buf[0] == 0 else 0
        idy_min, idx_min, idy_max, idx_max, idy, idx = coord[old_flag, :]
        np.copyto(  # update grid local
            dst=self.footprint[
                idy_min:idy_max,
                idx_min:idx_max,
            ],
            src=self.grid[
                idy_min:idy_max,
                idx_min:idx_max,
            ],
        )
        coord[old_flag, :] = 65535, 65535, 0, 0, 0, 0  # reset
        return idy, idx

    def _check_update(self) -> None:
        if self.base_price == 0.0:
            self._init_session()

        idy, idx = self._get_cords()
        self.check_patterns(idy=idy, idx=idx, footprint=self.footprint)

    @abstractmethod
    def check_patterns(
        self, idy: int, idx: int, footprint: NDArray[np.float64]
    ) -> None:
        pass


class BaseGridReader(GridReader):
    def check_patterns(
        self, idy: int, idx: int, footprint: NDArray[np.float64]
    ) -> None:
        # LocalLinks
        to_idy, to_idx = self.convert.to_idy, self.convert.to_idx  # noqa: F841
        to_price, to_timestamp = self.convert.to_price, self.convert.to_timestamp  # noqa: F841
        round_to_tick = self.convert.round_to_tick
        # - - -
        price: float = to_price(idy)
        _price, _qty = round_to_tick(price), footprint[idy, idx]
        print(_price, _qty, flush=True)
