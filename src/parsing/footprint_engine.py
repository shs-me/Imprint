import struct
import traceback

import numpy as np

from src.monitoring.monitor import MonitorObj


class FootprintEngine:
    def __init__(
        self,
        _mo_: MonitorObj,
        grid: np.ndarray,
        lines: int,
        columns: int,
        interval_min: int,
        tick_size: float,
    ):
        # Initialization
        self._mo_ = _mo_
        self._get, self._set, self._id_m_ = (
            self._mo_.get_,
            self._mo_.set_,
            self._mo_._status(daughter=True),
        )

        # grid init
        self.grid = grid  # 2-D. Array DType Float64
        self.lines = lines  # ID-Y in Array
        self.cols = columns  # ID-X in Array
        self.ivl_m = interval_min  # Interval cluster in minutes
        self.tick_size = tick_size  # tick size SYMBOL

        self.center = 0  # Index, Center array for + -
        self.ivl_ms = self.ivl_m * 60 * 1000  # Interval cluster in millisecond

        # Cluster Headers
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
        tick_size: float,
        _mo_: MonitorObj,
    ):
        try:
            grid = np.ndarray(
                ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                dtype=np.float64,
                buffer=_mo_.shms["grid"]["buf"],
            )
            grid[:] = 0.0
            return FootprintEngine(
                _mo_=_mo_,
                grid=grid,
                lines=cfg["grid"]["lines"],
                columns=cfg["grid"]["cols"],
                interval_min=cfg["grid"]["interval_min"],
                tick_size=tick_size,
            )

        except Exception:
            traceback.print_exc()
            _mo_.set_(_mo_._status(daughter=True), 150)  # Error in this func
            return None

    def _init_session(
        self,
        _id_m_,
        set_status,
        ivl_ms: int,
        lines: int,
        tick_size: float,
        grid: np.ndarray,
        OHLCV_T_D_CT: list,
        price: float,
        timestamp: int,
    ):  # Init Center, BasePrice, BaseTimestamp
        atip = int(price / tick_size)  # amount_ticks_in_price
        if atip > int(lines * 0.8):
            set_status(_id_m_, 100)  # Warn in this IF
            return

        self.center = atip if atip >= (lines - atip) else (lines - atip)

        grid[OHLCV_T_D_CT[0], 0] = price
        grid[OHLCV_T_D_CT[5], 0] = (timestamp // ivl_ms) * ivl_ms
        set_status(_id_m_, 11)  # Completed

    def update_headers(
        self,
        grid: np.ndarray,
        OHLCV_T_D_CT: list,
        idx: int,
        price: float,
        timestamp: int,
        qty: float,
        is_sell: bool,
    ):  # Update OHLC+V,CT,D,T
        if idx % 2 != 0:
            idx = idx - 1

        if grid[OHLCV_T_D_CT[7], idx] == 0.0:
            if idx != 0:
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

    def update(
        self,
        price: float,
        qty: float,
        is_sell: bool,
        timestamp: int,
    ):
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = (
            self._id_m_,
            self._set,
            self._get,
        )
        # FootprintEngine - LocalLink
        _grid, _lines, _cols, _ivl_m, _ivl_ms, _center, _tick_size, _OHLCV_T_D_CT = (
            self.grid,
            self.lines,
            self.cols,
            self.ivl_m,
            self.ivl_ms,
            self.center,
            self.tick_size,
            self.OHLCV_T_D_CT,
        )
        # Other - LocalLinks
        state = None
        # - - -
        if _grid[_OHLCV_T_D_CT[0], 0] == 0.0:
            self._init_session(
                _id_m_,
                _set_status,
                _ivl_ms,
                _lines,
                _tick_size,
                _grid,
                _OHLCV_T_D_CT,
                price,
                timestamp,
            )

        if _get_status(_id_m_):
            return

        idy = int((_grid[_OHLCV_T_D_CT[0], 0] - price) / _tick_size) + _center
        idx = ((timestamp - int(_grid[_OHLCV_T_D_CT[5], 0])) // _ivl_ms * 2) + (
            0 if is_sell else 1
        )

        if 0 <= idx < _grid.shape[1]:
            if 0 <= idy < _lines:
                _grid[idy, idx] += qty  # update cluster
                self.update_headers(
                    _grid,
                    _OHLCV_T_D_CT,
                    idx,
                    price,
                    timestamp,
                    qty,
                    is_sell,
                )

                state = struct.pack("<II", idy, idx)

            else:
                _set_status(_id_m_, 102)  # Warn in this IF
        else:
            _set_status(_id_m_, 101)  # Warn in this IF

        return state
