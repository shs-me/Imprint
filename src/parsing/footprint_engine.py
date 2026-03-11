import struct
from multiprocessing.synchronize import Event

import numpy as np

from src.utils import StatusAgent


class FootprintEngine:
    def __init__(
        self,
        sa: StatusAgent,
        id_m: int,
        grid: np.ndarray,
        lines: int,
        columns: int,
        interval_min: int,
        tick_size: float,
    ):
        # Initialization
        self._sa = sa
        self._set_status_, self._get_status_ = (
            self._sa._set_status,
            self._sa._get_status,
        )

        # grid init
        self.id_m = id_m  # Index this module on StatusSHM
        self.grid = grid  # 2-D. Array DType Float64
        self.lines = lines  # ID-Y in Array
        self.cols = columns  # ID-X in Array
        self.ivl_m = interval_min  # Interval cluster in minutes
        self.ts = tick_size  # tick size SYMBOL

        self.center = 0  # Index, Center array for + -
        self.ivl_ms = self.ivl_m * 60 * 1000  # Interval cluster in millisecond

        # Cluster Headers
        self.O = self.lines + 0  # Open price
        self.H = self.lines + 1  # High
        self.L = self.lines + 2  # Low
        self.C = self.lines + 3  # Close
        self.V = self.lines + 4  # Volume

        self.T = self.lines + 5  # Timestamp
        self.D = self.lines + 6  # Delta
        self.CT = self.lines + 7  # Count Trade

    @staticmethod
    def create(
        id_m: int,
        cfg: dict,
        tick_size: float,
        warn_error_status: Event,
    ):
        try:
            sa = StatusAgent(
                proc_name="parsing",
                config=cfg,
                warn_error_status=warn_error_status,
                daughter=True,
            )

            if isinstance(sa, StatusAgent):
                try:
                    grid = np.ndarray(
                        ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                        dtype=np.float64,
                        buffer=sa.shms["grid"]["buf"],
                    )
                    grid[:] = 0.0
                    sa._set_status(10)
                    return FootprintEngine(
                        sa=sa,
                        id_m=id_m,
                        grid=grid,
                        lines=cfg["grid"]["lines"],
                        columns=cfg["grid"]["cols"],
                        interval_min=cfg["grid"]["interval_min"],
                        tick_size=tick_size,
                    )

                except Exception:
                    sa._set_status(150)  # Error in this func
                    return None

        except Exception:
            return None

    def _init_session(
        self,
        price: float,
        timestamp: int,
    ):  # Init Center, BasePrice, BaseTimestamp
        self.atip = int(price / self.ts)  # amount_ticks_in_price
        if self.atip > int(self.lines * 0.8):
            self._set_status_(100)  # Warn in this IF
            return

        self.center = (
            self.atip
            if self.atip >= (self.lines - self.atip)
            else (self.lines - self.atip)
        )

        self.grid[self.O, 0] = price
        self.grid[self.T, 0] = (timestamp // self.ivl_ms) * self.ivl_ms
        self._set_status_(11)  # Completed

    def update_headers(
        self,
        idx,
        price,
        timestamp,
        qty,
        is_sell,
    ):  # Update OHLC+V,CT,D,T
        if idx % 2 != 0:
            idx = idx - 1

        if self.grid[self.CT, idx] == 0.0:
            if idx != 0:
                self.grid[self.O, idx] = price
                self.grid[self.T, idx] = timestamp

            self.grid[self.H, idx] = price
            self.grid[self.L, idx] = price

        if price > self.grid[self.H, idx]:
            self.grid[self.H, idx] = price

        if price < self.grid[self.L, idx]:
            self.grid[self.L, idx] = price

        self.grid[self.C, idx] = price
        self.grid[self.CT, idx] += 1.0
        self.grid[self.V, idx] += qty
        self.grid[self.D, idx] += -qty if is_sell else qty

    def update(
        self,
        price: float,
        qty: float,
        is_sell: bool,
        timestamp: int,
    ):  # Return Bytes OR NoneType
        if self.grid[self.O, 0] == 0.0:
            self._init_session(price, timestamp)

        if self._get_status_():
            return

        self._set_status_(1)  # Running

        idy = int((self.grid[self.O, 0] - price) / self.ts) + self.center
        idx = ((timestamp - int(self.grid[self.T, 0])) // self.ivl_ms * 2) + (
            0 if is_sell else 1
        )

        if 0 <= idx < self.grid.shape[1]:
            if 0 <= idy < self.lines:
                self.grid[idy, idx] += qty  # update cluster
                self.update_headers(idx, price, timestamp, qty, is_sell)

                self._set_status_(4)  # IDLE
                return struct.pack("<II", idy, idx)

            else:
                self._set_status_(102)  # Warn in this IF
                return
        else:
            self._set_status_(101)  # Warn in this IF
            return
