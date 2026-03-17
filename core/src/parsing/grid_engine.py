import struct
import traceback

import numpy as np

from .. import MonitorObj


class GridEngine:
    def __init__(
        self,
        _mo_: MonitorObj,
        grid: np.ndarray,
        cfg: dict,
        tick_size: float,
    ):
        # Initialization
        self.cfg = cfg
        self._mo_ = _mo_
        self._get, self._set, self._id_m_ = (
            self._mo_.get_,
            self._mo_.set_,
            self._mo_._status(daughter=True),
        )
        # grid init
        self.grid = grid  # 2-D. Array DType Float64
        self.lines = self.cfg["grid"]["lines"]  # ID-Y in Array
        self.cols = self.cfg["grid"]["cols"]  # ID-X in Array
        self.ivl_m = self.cfg["grid"]["interval_min"]  # Interval cluster in minutes
        self.tick_size = tick_size  # tick size SYMBOL
        # init session
        self.base_price = 0.0
        self.base_timestamp = 0
        self.center = 0  # Index, Center array for + -
        self.ivl_ms = self.ivl_m * 60 * 1000  # Interval cluster in millisecond
        # Offsets
        self._metrics_buf: memoryview = self._mo_.shms["metrics"]["buf"]
        self._id_y_x_offset: int = self.cfg["metrics"]["id_y_x"]
        self._flag_for_logic_offset: int = self.cfg["metrics"]["flag_for_logic"]
        self._base_price_timestamp_offset: int = self.cfg["metrics"][
            "base_price_and_timestamp"
        ]

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
            return GridEngine(
                _mo_=_mo_,
                grid=grid,
                cfg=cfg,
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
        _metrics_buf: memoryview,
        price: float,
        timestamp: int,
    ):  # Init Center, BasePrice, BaseTimestamp
        _bpat = self._base_price_timestamp_offset
        _flag = self._flag_for_logic_offset
        atip = int(price / tick_size)  # amount_ticks_in_price
        if atip <= int(lines * 0.8):
            self.center = atip if atip >= (lines - atip) else (lines - atip)
            self.base_price, self.base_timestamp = price, timestamp

            _metrics_buf[_bpat : (8 * 2 + _bpat)] = struct.pack(
                "!dq", price, ((timestamp // ivl_ms) * ivl_ms)
            )
            _metrics_buf[_flag] = 2
            return True

        else:
            set_status(_id_m_, 100)  # Warn in this IF
            return False

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
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get
        # Semaphore, SharedMemory, Arrays - LocalLinks
        _grid, _metrics_buf = self.grid, self._metrics_buf
        # ForLogic - LocalLinks

        _ids, _flag = self._id_y_x_offset, self._flag_for_logic_offset
        # BaseInit - LocalLinks
        _base_price, _base_timestamp = self.base_price, self.base_timestamp
        # FootprintEngine - LocalLink
        _lines, _cols, _ivl_m, _ivl_ms, _center, _tick_size, _OHLCV_T_D_CT = (
            self.lines,
            self.cols,
            self.ivl_m,
            self.ivl_ms,
            self.center,
            self.tick_size,
            self.OHLCV_T_D_CT,
        )
        # - - -

        if _get_status(_id_m_):
            return

        if _base_price == 0.0:
            if _state := self._init_session(
                _id_m_,
                _set_status,
                _ivl_ms,
                _lines,
                _tick_size,
                _metrics_buf,
                price,
                timestamp,
            ):
                _base_price, _base_timestamp = self.base_price, self.base_timestamp
            else:
                return

        idy: int = int((_base_price - price) / _tick_size) + _center
        idx: int = ((timestamp - _base_timestamp) // _ivl_ms * 2) + (
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
                if _metrics_buf[_flag] == 2:
                    _metrics_buf[_ids : (8 * 2 + _ids)] = struct.pack("!qq", idy, idx)
                    return True

            else:
                _set_status(_id_m_, 102)  # Warn in this IF
        else:
            _set_status(_id_m_, 101)  # Warn in this IF
