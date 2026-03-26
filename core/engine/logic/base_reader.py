import struct
import traceback

import numpy as np

from ... import Config, MonitorObj
from .. import ConvertMetrics


class BaseGridReader:
    def __init__(
        self,
        _mo_: MonitorObj,
        grid: np.ndarray,
        shm_grid: np.ndarray,
        lines: int,
        cols: int,
    ) -> None:
        # Initialization
        cfg = Config.CoreConfig()
        self._mo_ = _mo_
        self.shm_grid: np.ndarray = shm_grid  # 2-D. Array DType Float64
        self.grid: np.ndarray = grid  # 2-D. Array DType Float64
        self.lines: int = lines  # ID-Y in Array
        self.cols: int = cols  # ID-X in Array
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
        self.coords_slice1 = slice(*cfg.Metrics.coord_buf1)
        self.coords_slice2 = slice(*cfg.Metrics.coord_buf2)
        self.flag = cfg.Metrics.flag
        # SharedMemory
        self._metrics_buf = self._mo_.shms[cfg.Metrics.__name__]["buf"]

    @staticmethod
    def create(_mo_: MonitorObj) -> object | None:
        try:
            lines = Config.CoreConfig.Grid.lines + 8  # ID-Y in Array + 8 Headers
            cols = Config.CoreConfig.Grid.cols  # ID-X in Array
            shm_grid = np.ndarray(
                (lines, cols),
                dtype=np.float64,
                buffer=_mo_.shms[Config.CoreConfig.Grid.__name__]["buf"],
            )
            # Local Grid
            grid = np.ndarray((lines, cols), dtype=np.float64)
            grid[:] = 0.0
            return BaseGridReader(
                _mo_=_mo_, grid=grid, shm_grid=shm_grid, lines=lines, cols=cols
            )

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
        atip = round(self.base_price / self.tick_size)  # Amount Ticks In Price
        self.center = atip if atip >= (self.lines - atip) else (self.lines - atip)
        # Init Converter
        self.convert = ConvertMetrics(
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
        flag = self._metrics_buf[self.flag]
        coord_slice = self.coords_slice1 if flag == 0 else self.coords_slice2
        coords: tuple[int, int, int, int, int, int] = struct.unpack(
            "!HHHHHH", self._metrics_buf[coord_slice]
        )
        idy_min, idx_min, idy_max, idx_max, idy, idx = coords
        np.copyto(  # Update grid local
            self.grid[
                min(idy_min, idy_max) : max(idy_min, idy_max) + 1,
                min(idx_min, idx_max) : max(idx_min, idx_max) + 1,
            ],
            self.shm_grid[
                min(idy_min, idy_max) : max(idy_min, idy_max) + 1,
                min(idx_min, idx_max) : max(idx_min, idx_max) + 1,
            ],
        )
        # reset
        self._metrics_buf[coord_slice] = struct.pack(
            "!HHHHHH", 65535, 65535, 0, 0, 0, 0
        )
        # convert idy, idx to price, timestamp
        price, timestamp = (
            self.convert.to_price(idy),
            self.convert.to_timestamp(idx),
        )
        return (idy, idx, price, timestamp)

    def _check_update(self) -> bool:
        if self.base_price == 0.0:
            self._init_session()

        if (data := self._get_cords()) is not None:
            self.check_patterns(
                idy=data[0],
                idx=data[1],
                price=data[2],
                timestamp=data[3],
                grid=self.grid,
            )
            return True

        return False

    def check_patterns(
        self, idy: int, idx: int, price: float, timestamp: int, grid: np.ndarray
    ) -> None:
        _price = self.convert.round_to_tick(price)
        # print(idy, idx, _price, timestamp)  # debug
