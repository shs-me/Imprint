import struct
import traceback

import numpy as np

from ... import Config, MonitorObj
from .. import ConvertMetrics


class GridEngine:
    def __init__(
        self, _mo_: MonitorObj, grid: np.ndarray, lines: int, cols: int
    ) -> None:
        # Initialization
        cfg = Config.CoreConfig()
        self._mo_ = _mo_
        self._id_m_ = self._mo_._id_d
        self._set, self._get = self._mo_.set_, self._mo_.get_
        self.grid: np.ndarray = grid  # 2-D. Array DType Float64
        self.lines: int = lines  # ID-Y in Array
        self.cols: int = cols  # ID-X in Array
        self.ivl_m: int = cfg.Grid.interval_min
        self.tick_size: float = 0.0  # tick size SYMBOL
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
        self.base_price = 0.0
        self.base_timestamp = 0
        self.center = 0  # Index, Center array for + -
        self.ims = self.ivl_m * 60 * 1000  # Interval cluster in millisecond
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
            lines = Config.CoreConfig.Grid.lines  # ID-Y in Array
            cols = Config.CoreConfig.Grid.cols  # ID-X in Array
            grid = np.ndarray(
                ((lines + 8), cols),
                dtype=np.float64,
                buffer=_mo_.shms[Config.CoreConfig.Grid.__name__]["buf"],
            )
            return GridEngine(_mo_=_mo_, grid=grid, lines=lines, cols=cols)

        except Exception:
            traceback.print_exc()  # Debug
            _mo_.set_(_mo_._id_d, 150)  # Error in this func
            return None

    def _init_session(
        self, price: float, timestamp: int, id_m_: int, set_status
    ) -> bool:
        """Init Center, BasePrice, BaseTimestamp, TickSize"""
        self.tick_size = struct.unpack("!d", self._metrics_buf[self.tick_size_slice])[
            0
        ]  # Get TickSize from Buffer
        atip = round(price / self.tick_size)  # amount_ticks_in_price
        if atip <= round(self.lines * 0.8):
            self.center = atip if atip >= (self.lines - atip) else (self.lines - atip)
            self.base_price, self.base_timestamp = price, timestamp
            self._metrics_buf[self.bpat_slice] = struct.pack(
                "!dq", price, ((timestamp // self.ims) * self.ims)
            )
            # coord buf's init
            self._metrics_buf[self.coords_slice1] = struct.pack(
                "!HHHHHH", 65535, 65535, 0, 0, 0, 0
            )
            self._metrics_buf[self.coords_slice2] = struct.pack(
                "!HHHHHH", 65535, 65535, 0, 0, 0, 0
            )
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
            return True

        else:
            set_status(id_m_, 100)  # Warn in this IF
            return False

    def update_headers(
        self, idx: int, price: float, qty: float, timestamp: int, is_sell: bool
    ) -> None:
        """Update Headers Cluster: OHLC, Volume, CountTrades, Delta, Timestamp"""
        grid, OHLCV_T_D_CT = self.grid, self.OHLCV_T_D_CT
        # - - -
        if idx % 2 != 0:
            idx = idx - 1

        if grid[OHLCV_T_D_CT[7], idx] == 0.0:
            grid[OHLCV_T_D_CT[0], idx] = price
            grid[OHLCV_T_D_CT[5], idx] = timestamp

            grid[OHLCV_T_D_CT[1], idx] = price
            grid[OHLCV_T_D_CT[2], idx] = price

        if price > grid[OHLCV_T_D_CT[1], idx]:
            grid[OHLCV_T_D_CT[1], idx] = price

        if price < grid[OHLCV_T_D_CT[2], idx]:
            grid[OHLCV_T_D_CT[2], idx] = price

        grid[OHLCV_T_D_CT[3], idx] = price
        grid[OHLCV_T_D_CT[7], idx] += 1.0
        grid[OHLCV_T_D_CT[4], idx] += qty
        grid[OHLCV_T_D_CT[6], idx] += -qty if is_sell else qty

    def set_cords(self, idy: int, idx: int) -> bool | None:
        """Set Coordinates IDY:IDX on 2-D Array 'Cord'"""
        while range(2):
            flag = self._metrics_buf[self.flag]
            coord_slice = self.coords_slice1 if flag == 0 else self.coords_slice2
            coords: tuple[int, int, int, int, int, int] = struct.unpack(
                "!HHHHHH", self._metrics_buf[coord_slice]
            )
            idy_min, idx_min, idy_max, idx_max, __, _ = coords
            if idy < idy_min:  # True: Update IDY MIN
                idy_min = idy
            if idy > idy_max:  # True: Update IDY MAX
                idy_max = idy
            if idx < idx_min:  # True: Update IDX MIN
                idx_min = idx
            if idx > idx_max:  # True: Update IDX MAX
                idx_max = idx
            if self._metrics_buf[self.flag] == flag:
                self._metrics_buf[coord_slice] = struct.pack(
                    "!HHHHHH", idy_min, idx_min, idy_max, idx_max, idy, idx
                )
                return True

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        """Update GridArray"""
        # MonitorObj - LocalLink
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get
        if _get_status(_id_m_):
            return False

        if self.base_price == 0.0:
            if (
                self._init_session(
                    price=price,
                    timestamp=timestamp,
                    id_m_=_id_m_,
                    set_status=_set_status,
                )
                is False
            ):
                return False

        idy: int | None = self.convert.to_idy(price=price)
        idx: int | None = self.convert.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.grid[idy, idx] += qty  # update cluster
                self.update_headers(
                    idx=idx,
                    price=price,
                    qty=qty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                )
                if self.set_cords(idy, idx):
                    return True

            else:
                _set_status(_id_m_, 102)  # Warn in this IF
        else:
            _set_status(_id_m_, 101)  # Warn in this IF

        return False
