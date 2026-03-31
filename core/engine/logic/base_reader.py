import traceback
from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from ... import Config, MonitorObj
from .. import ConvertMetrics


class BaseGridReader:
    def __init__(
        self,
        mo: MonitorObj,
        guarantee: Event,
        grid: NDArray[np.float64],
        _grid: NDArray[np.float64],
        _coord: NDArray[np.uint16],
    ) -> None:
        __cfg, self._mo, self.guarantee = Config.CoreConfig, mo, guarantee
        self.grid, self._grid, self._coord = grid, _grid, _coord
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

    @staticmethod
    def create(_mo_: MonitorObj, guarantee: Event) -> object | None:
        try:
            __cfg: type[Config.CoreConfig] = Config.CoreConfig
            _grid: NDArray[np.float64] = np.ndarray(
                shape=((__cfg.Grid.lines + 8), __cfg.Grid.cols),
                dtype=np.float64,
                buffer=_mo_.shms[__cfg.Grid.__name__]["buf"],
            )
            grid: NDArray[np.float64] = np.ndarray(
                shape=((__cfg.Grid.lines + 8), __cfg.Grid.cols),
                dtype=np.float64,
            )
            _coord: NDArray[np.uint16] = np.ndarray(
                shape=(
                    __cfg.Metrics.coord_lines,
                    __cfg.Metrics.coord_cols,
                ),
                dtype=np.uint16,
                buffer=_mo_.shms[__cfg.Metrics.__name__]["buf"][
                    __cfg.Metrics.coord_offset[0] : __cfg.Metrics.coord_offset[1]
                ],
            )
            return BaseGridReader(
                mo=_mo_, guarantee=guarantee, grid=grid, _grid=_grid, _coord=_coord
            )

        except Exception:
            traceback.print_exc()  # Debug
            return None

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
        new_flag: int = 1 if (flag := self.metrics_buf[self.flag]) == 0 else 0
        self.metrics_buf[self.flag] = new_flag  # change active buffer for writer
        if self.guarantee.is_set() is not False:
            self.guarantee.clear()  # active buffer is empty

        _counter, sim_time_ns = 0, 1000
        while _counter < sim_time_ns:
            if (self._coord[flag, 6] % 2) == 0:  # data is not dirty
                idy_min, idx_min, idy_max, idx_max, idy, idx = self._coord[flag, :6]
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
                self._coord[flag, :] = 65535, 65535, 0, 0, 0, 0, 0  # reset
                price, timestamp = (  # convert idy, idx to price, timestamp
                    self.convert.to_price(idy=int(idy)),
                    self.convert.to_timestamp(idx=int(idx)),
                )
                return (idy, idx, price, timestamp)

            else:  # data maybe is dirty
                _counter += 1

        return None

    def _check_update(self) -> bool:
        if self.base_price == 0.0:
            self._init_session()

        if (data := self._get_cords()) is not None:
            self.check_patterns(
                idy=data[0], idx=data[1], price=data[2], timestamp=data[3]
            )
            return True

        return False

    def check_patterns(self, idy: int, idx: int, price: float, timestamp: int) -> None:
        _price: int | float = self.convert.round_to_tick(price)
        print(idy, idx, _price, timestamp, flush=True)  # debug
