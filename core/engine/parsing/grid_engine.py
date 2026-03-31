import traceback
from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from ... import Config, MonitorObj
from .. import ConvertMetrics


class GridEngine:
    def __init__(
        self,
        mo: MonitorObj,
        guarantee: Event,
        grid: NDArray[np.float64],
        coord: NDArray[np.uint16],
    ) -> None:
        __cfg, self._mo, self.guarantee = Config.CoreConfig, mo, guarantee
        self.id_m = self._mo.id_d
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.grid, self.coord = grid, coord
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
            __cfg = Config.CoreConfig
            grid = np.ndarray(
                ((__cfg.Grid.lines + 8), __cfg.Grid.cols),
                dtype=np.float64,
                buffer=_mo_.shms[__cfg.Grid.__name__]["buf"],
            )
            coord = np.ndarray(
                (
                    __cfg.Metrics.coord_lines,
                    __cfg.Metrics.coord_cols,
                ),
                dtype=np.uint16,
                buffer=_mo_.shms[__cfg.Metrics.__name__]["buf"][
                    __cfg.Metrics.coord_offset[0] : __cfg.Metrics.coord_offset[1]
                ],
            )
            return GridEngine(mo=_mo_, guarantee=guarantee, grid=grid, coord=coord)

        except Exception:
            traceback.print_exc()  # Debug
            _mo_.set_status(id_m=_mo_.id_d, code=150)  # Error in this func
            return None

    def _init_session(self, price: float, timestamp: int) -> bool:
        """Init Center, BasePrice, BaseTimestamp, TickSize"""
        self.tick_size = self.tick_size_buf[0]
        atip = round(price / self.tick_size)  # amount_ticks_in_price
        if atip <= round(self.lines * 0.8):
            self.center = atip if atip >= (self.lines - atip) else (self.lines - atip)
            self.base_price_buf[0] = self.base_price = price
            self.base_timestamp_buf[0] = self.base_timestamp = timestamp
            self.coord[:] = 65535, 65535, 0, 0, 0, 0, 1, 0
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
            self.set_status(self.id_m, 100)  # Warn in this IF
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

    def set_cords(self, idy: int, idx: int) -> None:
        """Set Coordinates IDY:IDX on 2-D Array 'Cord'"""
        metrics_buf, coord = self.metrics_buf, self.coord
        # - - -
        flag: int = metrics_buf[self.flag]
        coord[flag, 6] = 1  # data maybe is dirty
        coords = coord[flag, :4]
        idy_min = idy if coords[0] > idy else coords[0]
        idx_min = idx if coords[1] > idx else coords[1]
        idy_max = idy + 1 if coords[2] < idy else coords[2]
        idx_max = idx + 1 if coords[3] < idx else coords[3]
        coord[flag, :6] = idy_min, idx_min, idy_max, idx_max, idy, idx
        coord[flag, 6] = 0  # data is not dirty

        if (nflag := metrics_buf[self.flag]) != flag:
            if coord[flag, 7] == 0 and coord[flag, 0] != 65535:
                self.coord[flag, :7] = 65535, 65535, 0, 0, 0, 0, 1
                self.coord[nflag, :7] = idy_min, idx_min, idy_max, idx_max, idy, idx, 0

        if self.guarantee.is_set() is False:
            self.guarantee.set()  # active buffer is not empty

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        """Update GridArray"""
        if self.have_problem(self.id_m):
            return False

        if self.base_price == 0.0:
            if self._init_session(price=price, timestamp=timestamp) is False:
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
                self.set_cords(idy, idx)
                return True

            else:
                self.set_status(id_m=self.id_m, code=102)  # Warn in this IF
        else:
            self.set_status(id_m=self.id_m, code=101)  # Warn in this IF

        return False
