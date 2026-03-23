import struct
import traceback
from multiprocessing.synchronize import Event

import numpy as np

from .. import ConvertMetrics, MonitorObj


class BaseGridReader:
    def __init__(
        self,
        cfg: dict,
        _mo_: MonitorObj,
        writer_sleep: Event,
        grid: np.ndarray,
        shm_grid: np.ndarray,
    ) -> None:
        # Initialization
        self.cfg = cfg
        self._mo_ = _mo_
        # Grid init
        self.shm_grid: np.ndarray = shm_grid  # 2-D. Array DType Float64
        self.grid: np.ndarray = grid  # 2-D. Array DType Float64
        self.lines: int = self.cfg["grid"]["lines"]  # ID-Y in Array
        self.cols: int = self.cfg["grid"]["cols"]  # ID-X in Array
        self.ivl_m: int = self.cfg["grid"][
            "interval_min"
        ]  # Interval cluster in minutes
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
        self.tick_size: float = 0.0  # tick size SYMBOL
        self.center: int = 0  # Index, Center array for + -
        self.ims: int = self.ivl_m * 60 * 1000  # Interval cluster in millisecond
        # MetricsSHM
        self._base_price_timestamp_offset: int = self.cfg["metrics"][
            "base_price_and_timestamp"
        ]
        self._ts_id: int = self.cfg["metrics"]["tick_size"]
        self._metrics_buf: memoryview = self._mo_.shms["metrics"]["buf"]
        # Cord init
        self.coord_offset: int = self.cfg["metrics"]["coord_offset"]
        self.writer_sleep: Event = writer_sleep

    @staticmethod
    def create(
        cfg: dict,
        _mo_: MonitorObj,
        writer_sleep: Event,
    ) -> object | None:
        try:
            shm_grid = np.ndarray(
                ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                dtype=np.float64,
                buffer=_mo_.shms["grid"]["buf"],
            )
            # Local Grid
            grid = np.ndarray(
                ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                dtype=np.float64,
            )
            grid[:] = 0.0
            return BaseGridReader(
                cfg=cfg,
                _mo_=_mo_,
                writer_sleep=writer_sleep,
                grid=grid,
                shm_grid=shm_grid,
            )

        except Exception:
            traceback.print_exc()  # Debug
            return None

    # Get Center, BasePrice, BaseTimestamp, TickSize
    def _init_session(
        self,
    ) -> bool:
        bpat = self._base_price_timestamp_offset
        # - - -
        self.tick_size = struct.unpack(
            "!d", self._metrics_buf[self._ts_id : self._ts_id + 8]
        )[0]  # Get TickSize from Buffer
        temp: tuple[float, int] = struct.unpack(
            "!dq", self._metrics_buf[bpat : (8 * 2 + bpat)]
        )  # Get TickSize from Buffer
        self.base_price, self.base_timestamp = temp[0], temp[1]
        atip = round(self.base_price / self.tick_size)  # amount_ticks_in_price
        self.center = atip if atip >= (self.lines - atip) else (self.lines - atip)
        # Init Converter
        self.convert: ConvertMetrics = ConvertMetrics(
            tick_size=self.tick_size,
            base_price=self.base_price,
            base_timestamp=self.base_timestamp,
            center=self.center,
            lines=self.lines,
            cols=self.cols,
            ims=self.ims,
        )

        return True

    # Get Coordinaties IDY:IDX from 2-D Array "Cord"
    def _get_cords(
        self,
    ) -> tuple[int, int, float, int] | None:
        _metrics_buf, _writer_sleep = self._metrics_buf, self.writer_sleep
        _offset = self.coord_offset
        # - - -
        # get XYZ for slice
        _writer_sleep.set()
        coords: tuple[int, int, int, int, int, int] = struct.unpack(
            "!HHHHHH", _metrics_buf[_offset : _offset + 12]
        )
        idy_min, idx_min, idy_max, idx_max, idy, idx = coords
        # update grid local
        np.copyto(
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
        _metrics_buf[_offset : _offset + 12] = struct.pack(
            "!HHHHHH", 65535, 65535, 0, 0, 0, 0
        )
        _writer_sleep.clear()
        # convert idy, idx to price, timestamp
        price, timestamp = (
            self.convert.to_price(idy),
            self.convert.to_timestamp(idx),
        )
        return (idy, idx, price, timestamp)

    # Start
    def _check_update(
        self,
    ) -> bool:
        if self.base_price == 0.0:
            if self._init_session() is False:
                return False

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
        self,
        idy: int,
        idx: int,
        price: float,
        timestamp: int,
        grid: np.ndarray,
    ):
        _price = self.convert.round_to_tick(price)
        # print(idy, idx, _price, timestamp)  # debug
