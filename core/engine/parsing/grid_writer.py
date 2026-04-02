import traceback
from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from ... import Config, MonitorObj
from .. import ConvertMetrics


class GridWriter:
    def __init__(self, mo: MonitorObj, guarantee: Event) -> None:
        __cfg, self._mo, self.guarantee = Config.CoreConfig, mo, guarantee
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
            self.grid: NDArray[np.float64] = np.ndarray(
                shape=((self.lines + 8), self.cols),
                dtype=np.float64,
                buffer=self._mo.grid_buf,
            )
            self.coord: NDArray[np.int32] = np.ndarray(
                shape=(__cfg.Metrics.coord_lines, __cfg.Metrics.coord_cols),
                dtype=np.int32,
                buffer=self._mo.metrics_buf[slice(*__cfg.Metrics.coord_offset)],
            )
        except Exception:
            traceback.print_exc()  # Debug
            self.set_status(id_m=self.id_m, code=150)  # Error in this func

    def _init_session(self, price: float, timestamp: int) -> bool:
        """Init Center, BasePrice, BaseTimestamp, TickSize"""
        self.tick_size: float = self.tick_size_buf[0]
        atip: int = round(number=price / self.tick_size)  # amount_ticks_in_price
        if atip >= round(number=self.lines * 0.8):
            self.set_status(id_m=self.id_m, code=100)  # Warn in this IF
            return False

        self.center: int = atip if atip >= (self.lines - atip) else (self.lines - atip)
        self.base_price_buf[0] = self.base_price = price
        self.base_timestamp_buf[0] = self.base_timestamp = timestamp
        self.coord[:] = 65535, 65535, 0, 0, 0, 0
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

    def _update_headers(
        self, idx: int, price: float, qty: float, timestamp: int, is_sell: bool
    ) -> None:
        """Update Headers Cluster: OHLC, Volume, CountTrades, Delta, Timestamp"""
        grid, OHLCV_T_D_CT = self.grid, self.OHLCV_T_D_CT
        # - - -
        _idx: int = idx - 1 if idx % 2 != 0 else idx

        if grid[OHLCV_T_D_CT[7], _idx] == 0.0:
            grid[OHLCV_T_D_CT[0], _idx] = price
            grid[OHLCV_T_D_CT[5], _idx] = timestamp

        if price > grid[OHLCV_T_D_CT[1], _idx]:
            grid[OHLCV_T_D_CT[1], _idx] = price

        if price < grid[OHLCV_T_D_CT[2], idx]:
            grid[OHLCV_T_D_CT[2], _idx] = price

        grid[OHLCV_T_D_CT[3], _idx] = price
        grid[OHLCV_T_D_CT[7], _idx] += 1.0
        grid[OHLCV_T_D_CT[4], _idx] += qty
        grid[OHLCV_T_D_CT[6], _idx] += -qty if is_sell else qty

    def _set_cords(self, idy: int, idx: int) -> None:
        """Set Coordinates IDY:IDX on 2-D Array 'Cord'"""
        coord = self.coord
        # - - -
        new_flag: int = 1 if (flag := self.flag_buf[0]) == 0 else 0
        coords: NDArray[np.int32] = coord[flag, :4]
        idy_min: int | np.int32 = idy if coords[0] > idy else coords[0]
        idx_min: int | np.int32 = idx if coords[1] > idx else coords[1]
        idy_max: int | np.int32 = idy + 1 if coords[2] <= idy else coords[2]
        idx_max: int | np.int32 = idx + 1 if coords[3] <= idx else coords[3]
        coord[flag, :] = idy_min, idx_min, idy_max, idx_max, idy, idx

        if self.guarantee.is_set() is False:
            self.flag_buf[0] = new_flag
            self.guarantee.set()

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        if self.base_price == 0.0:
            if self._init_session(price=price, timestamp=timestamp) is False:
                return False

        idy: int | None = self.convert.to_idy(price=price)
        idx: int | None = self.convert.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.grid[idy, idx] += qty  # update cluster
                self._update_headers(
                    idx=idx,
                    price=price,
                    qty=qty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                )
                self._set_cords(idy, idx)
                return True

            else:
                self.set_status(id_m=self.id_m, code=102)  # Warn in this IF
        else:
            self.set_status(id_m=self.id_m, code=101)  # Warn in this IF

        return False
