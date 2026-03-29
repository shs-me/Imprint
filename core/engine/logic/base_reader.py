import struct
import traceback

import numpy as np
from numpy.typing import NDArray

from ... import Config, MonitorObj
from .. import ConvertMetrics


class BaseGridReader:
    def __init__(
        self,
        _mo_: MonitorObj,
        grid: NDArray[np.float64],
        _grid: NDArray[np.float64],
        _coord: NDArray[np.uint16],
    ) -> None:
        cfg = Config.CoreConfig
        self._mo_ = _mo_
        self.grid = grid
        self._grid = _grid
        self._coord = _coord
        self.lines: int = cfg.Grid.lines  # ID-Y in Array
        self.cols: int = cfg.Grid.cols  # ID-X in Array
        self.ivl_m: int = cfg.Grid.interval_min
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
        # Init session
        self.base_price: float = 0.0
        self.base_timestamp: int = 0
        self.tick_size: float = 0.0
        self.center: int = 0  # Index, Center array for + -
        self.ims: int = self.ivl_m * 60 * 1000  # Interval cluster in millisecond
        # MetricsSHM
        self.bpat_slice = slice(*cfg.Metrics.base_price_and_timestamp)
        self.tick_size_slice = slice(*cfg.Metrics.tick_size)
        self.flag = cfg.Metrics.flag
        # SharedMemory
        self._metrics_buf = self._mo_.shms[cfg.Metrics.__name__]["buf"]

    @staticmethod
    def create(_mo_: MonitorObj) -> object | None:
        try:
            cfg: type[Config.CoreConfig] = Config.CoreConfig
            _grid: NDArray[np.float64] = np.ndarray(
                shape=((cfg.Grid.lines + 8), cfg.Grid.cols),
                dtype=np.float64,
                buffer=_mo_.shms[cfg.Grid.__name__]["buf"],
            )
            grid: NDArray[np.float64] = np.ndarray(
                shape=((cfg.Grid.lines + 8), cfg.Grid.cols),
                dtype=np.float64,
            )
            _coord: NDArray[np.uint16] = np.ndarray(
                shape=(
                    cfg.Metrics.coord_lines,
                    cfg.Metrics.coord_cols,
                ),
                dtype=np.uint16,
                buffer=_mo_.shms[cfg.Metrics.__name__]["buf"][
                    cfg.Metrics.coord_offset[0] : cfg.Metrics.coord_offset[1]
                ],
            )
            return BaseGridReader(_mo_=_mo_, grid=grid, _grid=_grid, _coord=_coord)

        except Exception:
            traceback.print_exc()  # Debug
            return None

    def _init_session(self) -> None:
        """Get BasePrice, BaseTimestamp, TickSize"""
        self.tick_size = struct.unpack("!d", self._metrics_buf[self.tick_size_slice])[0]
        temp: tuple[float, int] = struct.unpack(
            "!dq", self._metrics_buf[self.bpat_slice]
        )
        self.base_price, self.base_timestamp = temp[0], temp[1]
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
        new_flag: int = 1 if (flag := self._metrics_buf[self.flag]) == 0 else 0
        self._metrics_buf[self.flag] = new_flag  # change buffer for writer
        _counter: int = 0
        while _counter < 2:
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
