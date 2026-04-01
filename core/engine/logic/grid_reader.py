import traceback
from abc import ABC, abstractmethod
from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from ... import Config, MonitorObj
from .. import ConvertMetrics


class GridReader(ABC):
    def __init__(self, mo: MonitorObj, guarantee: Event) -> None:
        __cfg, self._mo, self.guarantee = Config.CoreConfig, mo, guarantee
        self.id_m = self._mo.id_d
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.lines, self.cols = __cfg.Grid.lines, __cfg.Grid.cols
        self.OHLCV_T_D_CT = [
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
        self.center, self.ims = 0, __cfg.Grid.interval_min * 60 * 1000
        self.flag = __cfg.Metrics.flag
        self.metrics_buf = self._mo.shms[__cfg.Metrics.__name__]["buf"]
        self.tick_size_buf = self.metrics_buf[
            __cfg.Metrics.tick_size[0] : __cfg.Metrics.tick_size[1]
        ].cast("d")
        self.base_price_buf = self.metrics_buf[
            __cfg.Metrics.base_price[0] : __cfg.Metrics.base_price[1]
        ].cast("d")
        self.base_timestamp_buf = self.metrics_buf[
            __cfg.Metrics.base_timestamp[0] : __cfg.Metrics.base_timestamp[1]
        ].cast("q")

        self._init_array()

    def _init_array(self) -> None:
        try:
            __cfg = Config.CoreConfig
            self.grid: NDArray[np.float64] = np.ndarray(
                shape=((self.lines + 8), self.cols),
                dtype=np.float64,
            )
            self.grid[:] = 0.0
            self._grid: NDArray[np.float64] = np.ndarray(
                ((self.lines + 8), self.cols),
                dtype=np.float64,
                buffer=self._mo.shms[__cfg.Grid.__name__]["buf"],
            )
            self._coord: NDArray[np.uint16] = np.ndarray(
                (
                    __cfg.Metrics.coord_lines,
                    __cfg.Metrics.coord_cols,
                ),
                dtype=np.uint16,
                buffer=self.metrics_buf[
                    __cfg.Metrics.coord_offset[0] : __cfg.Metrics.coord_offset[1]
                ],
            )
        except Exception:
            traceback.print_exc()  # Debug
            self.set_status(id_m=self.id_m, code=150)  # Error in this func

    def _init_session(self) -> None:
        """Get BasePrice, BaseTimestamp, TickSize"""
        self.tick_size = self.tick_size_buf[0]
        self.base_price = self.base_price_buf[0]
        self.base_timestamp = self.base_timestamp_buf[0]

        atip: int = round(  # Amount Ticks In Price
            number=self.base_price / self.tick_size
        )
        self.center = atip if atip >= (self.lines - atip) else (self.lines - atip)
        self.convert: ConvertMetrics = ConvertMetrics(
            tick_size=self.tick_size,
            base_price=self.base_price,
            base_timestamp=self.base_timestamp,
            center=self.center,
            lines=self.lines,
            cols=self.cols,
            ims=self.ims,
        )

    def _get_cords(self) -> tuple[int, int, float, int] | None:
        """Get Coordinaties IDY:IDX from 2-D Array 'Cord'"""
        metrics_buf, coord = self.metrics_buf, self._coord
        # - - -
        old_flag: int = 1 if metrics_buf[self.flag] == 0 else 0
        idy_min, idx_min, idy_max, idx_max, idy, idx = coord[old_flag, :]
        np.copyto(  # update grid local
            dst=self.grid[
                idy_min:idy_max,
                idx_min:idx_max,
            ],
            src=self._grid[
                idy_min:idy_max,
                idx_min:idx_max,
            ],
        )
        coord[old_flag, :] = 65535, 65535, 0, 0, 0, 0  # reset
        price, timestamp = (  # convert idy, idx to price, timestamp
            self.convert.to_price(idy=int(idy)),
            self.convert.to_timestamp(idx=int(idx)),
        )
        return (idy, idx, price, timestamp)

    def _check_update(self) -> bool:
        if self.base_price == 0.0:
            self._init_session()

        if (data := self._get_cords()) is not None:
            self.check_patterns(
                idy=data[0], idx=data[1], price=data[2], timestamp=data[3]
            )
            return True

        return False

    @abstractmethod
    def check_patterns(self, idy: int, idx: int, price: float, timestamp: int) -> None:
        pass


class BaseGridReader(GridReader):
    def check_patterns(self, idy: int, idx: int, price: float, timestamp: int) -> None:
        _price: int | float = self.convert.round_to_tick(price)
        print(idy, idx, _price, timestamp, flush=True)  # debug
        if self.guarantee.is_set():
            self.guarantee.set()
