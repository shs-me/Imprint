import struct
import traceback

import numpy as np

from .. import ConvertMetrics, MonitorObj


class BaseGridReader:
    def __init__(
        self,
        _mo_: MonitorObj,
        grid: np.ndarray,
        cord: np.ndarray,
        shm_grid: np.ndarray,
        cfg: dict,
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
        self.tick_size: float = 0.0  # tick size SYMBOL
        # Init session
        self.base_price = 0.0
        self.base_timestamp = 0
        self.center = 0  # Index, Center array for + -
        self.ims = self.ivl_m * 60 * 1000  # Interval cluster in millisecond
        # MetricsSHM
        self._base_price_timestamp_offset: int = self.cfg["metrics"][
            "base_price_and_timestamp"
        ]
        self._ts_id: int = self.cfg["metrics"]["tick_size"]
        self._metrics_buf: memoryview = self._mo_.shms["metrics"]["buf"]
        # Cord init
        self.cord: np.ndarray = cord
        self._ac: int = self.cfg["metrics"]["flag_r"]
        self._flag_r: int = self.cfg["metrics"]["flag_r"]
        self._flag_w: int = self.cfg["metrics"]["flag_w"]

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

    @staticmethod
    def create(
        cfg: dict,
        _mo_: MonitorObj,
    ) -> object | None:
        try:
            shm_grid = np.ndarray(
                ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                dtype=np.float64,
                buffer=_mo_.shms["grid"]["buf"],
            )
            shm_grid[:] = 0.0
            # Local Grid
            grid = np.ndarray(
                ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                dtype=np.float64,
            )
            grid[:] = 0.0
            # Coordinaties
            cord = np.ndarray(
                ((cfg["metrics"]["lines"]), cfg["metrics"]["cols"]),
                dtype=np.int32,
                buffer=_mo_.shms["metrics"]["buf"],
                offset=4096,
            )
            cord[:] = 0
            return BaseGridReader(
                _mo_=_mo_,
                grid=grid,
                cord=cord,
                shm_grid=shm_grid,
                cfg=cfg,
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
    ) -> tuple[int, int, float, int]:
        _metrics_buf, _cord = self._metrics_buf, self.cord
        _flag_r, _flag_w = self._flag_r, self._flag_w
        # - - -
        # get start/end idy, idx
        _row_w = _metrics_buf[_flag_w]  # get row where writer stopped
        _row_r = _metrics_buf[_flag_r]  # get row where reader stopped
        if _row_r > _row_w:
            _row_r = 0

        idy_s, idy_e = _cord[_row_r, 0], _cord[_row_w - 1, 0]
        idx_s, idx_e = _cord[_row_r, 1], _cord[_row_w - 1, 1]
        # update grid local
        self.grid[idy_s:idy_e, idx_s:idx_e] = self.shm_grid[idy_s:idy_e, idx_s:idx_e]
        _metrics_buf[_flag_r] = _row_w
        # convert idy, idx to price, timestamp
        price, timestamp = (
            self.convert.to_price(idy_e),
            self.convert.to_timestamp(idx_e),
        )
        return (idy_e, idx_e, price, timestamp)

    # Start
    def _check_update(
        self,
    ) -> bool:
        if self.base_price == 0.0:
            if self._init_session() is False:
                return False

        _idy, _idx, _price, _timestamp = self._get_cords()
        self.check_patterns(
            idy=_idy,
            idx=_idx,
            price=_price,
            timestamp=_timestamp,
            grid=self.grid,
        )
        return True

    def check_patterns(
        self,
        idy: int,
        idx: int,
        price: float,
        timestamp: int,
        grid: np.ndarray,
    ):
        print(idy, idx, price, timestamp)
