import struct
import traceback
from multiprocessing.synchronize import Event

import numpy as np

from .. import ConvertMetrics, MonitorObj


class GridEngine:
    def __init__(
        self,
        cfg: dict,
        _mo_: MonitorObj,
        wait_reader: Event,
        grid: np.ndarray,
    ) -> None:
        # Initialization
        self.cfg = cfg
        self._mo_ = _mo_
        self._get, self._set, self._id_m_ = (
            self._mo_.get_,
            self._mo_.set_,
            self._mo_._status(daughter=True),
        )
        # Grid init
        self.grid: np.ndarray = grid  # 2-D. Array DType Float64
        self.lines: int = self.cfg["grid"]["lines"]  # ID-Y in Array
        self.cols: int = self.cfg["grid"]["cols"]  # ID-X in Array
        self.ivl_m: int = self.cfg["grid"][
            "interval_min"
        ]  # Interval cluster in minutes
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
        self._base_price_timestamp_offset: int = self.cfg["metrics"][
            "base_price_and_timestamp"
        ]
        self._ts_id: int = self.cfg["metrics"]["tick_size"]
        self._metrics_buf: memoryview = self._mo_.shms["metrics"]["buf"]
        # Cord init
        self.coord_offset: int = self.cfg["metrics"]["coord_offset"]
        self.wait_reader: Event = wait_reader

    @staticmethod
    def create(
        cfg: dict,
        _mo_: MonitorObj,
        wait_reader: Event,
    ) -> object | None:
        try:
            grid = np.ndarray(
                ((cfg["grid"]["lines"] + 8), cfg["grid"]["cols"]),
                dtype=np.float64,
                buffer=_mo_.shms["grid"]["buf"],
            )
            return GridEngine(
                cfg=cfg,
                _mo_=_mo_,
                grid=grid,
                wait_reader=wait_reader,
            )

        except Exception:
            traceback.print_exc()  # Debug
            _mo_.set_(_mo_._status(daughter=True), 150)  # Error in this func
            return None

    # Init Center, BasePrice, BaseTimestamp, TickSize
    def _init_session(
        self,
        _id_m_,
        set_status,
        price: float,
        timestamp: int,
    ) -> bool:
        _bpat = self._base_price_timestamp_offset
        # - - -
        self.tick_size = struct.unpack(
            "!d", self._metrics_buf[self._ts_id : self._ts_id + 8]
        )[0]  # Get TickSize from Buffer
        atip = round(price / self.tick_size)  # amount_ticks_in_price
        if atip <= round(self.lines * 0.8):
            self.center = atip if atip >= (self.lines - atip) else (self.lines - atip)
            self.base_price, self.base_timestamp = price, timestamp
            self._metrics_buf[_bpat : (8 * 2 + _bpat)] = struct.pack(
                "!dq", price, ((timestamp // self.ims) * self.ims)
            )

            # coord
            self._metrics_buf[self.coord_offset : self.coord_offset + 12] = struct.pack(
                "!HHHHHH", 65535, 65535, 0, 0, 0, 0
            )

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

        else:
            set_status(_id_m_, 100)  # Warn in this IF
            return False

    # Update Headers Cluster: Data OHLC,V,CT,D,T
    def update_headers(
        self,
        idx: int,
        price: float,
        qty: float,
        timestamp: int,
        is_sell: bool,
    ) -> None:
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

    # Set Coordinates IDY:IDX on 2-D Array "Cord"
    def set_cords(
        self,
        idy: int,
        idx: int,
    ) -> bool | None:
        _metrics_buf, _wait_reader = self._metrics_buf, self.wait_reader
        _offset = self.coord_offset
        # - - -
        while _wait_reader.is_set():  # Reader work
            pass

        coords: tuple[int, int, int, int] = struct.unpack(
            "!HHHH", _metrics_buf[_offset : _offset + 8]
        )
        idy_min, idx_min, idy_max, idx_max = coords
        if idy < idy_min:
            idy_min = idy
        if idy > idy_max:
            idy_max = idy
        if idx < idx_min:
            idx_min = idx
        if idx > idx_max:
            idx_max = idx

        _metrics_buf[_offset : _offset + 12] = struct.pack(
            "!HHHHHH", idy_min, idx_min, idy_max, idx_max, idy, idx
        )
        print(idy_min, idx_min, idy_max, idx_max, idy, idx)
        return True

    def update(
        self,
        price: float,
        qty: float,
        is_sell: bool,
        timestamp: int,
    ) -> bool:
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get

        if _get_status(_id_m_):
            return False

        if self.base_price == 0.0:
            if (
                self._init_session(
                    _id_m_,
                    _set_status,
                    price,
                    timestamp,
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
