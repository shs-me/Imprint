"""Footprint grid updates and shared memory double-buffering writer routines."""

import os
import time

import numpy as np
from numba import njit
from numpy import float64, int64
from numpy.typing import NDArray

from ... import constant as c
from ...settings import BarHeadersMetadata, SpaceCoords
from ...settings import StatusCodes as scs
from ...utils.monitoring.agent_manager import AgentManager
from .utils.fp_converter import FPconverter

BHM_VWAP_W: int = int(BarHeadersMetadata.VWAP_W)
BHM_VWAP_PW: int = int(BarHeadersMetadata.VWAP_PW)
BHM_VWAP_P2W: int = int(BarHeadersMetadata.VWAP_P2W)
BHM_ConstantCount: int = int(BarHeadersMetadata._ConstantCount)


class FootprintWriter:
    """Base class managing tick ingestion, VWAP variance accumulation, and memory double-buffering."""

    def __init__(self, manager: AgentManager) -> None:
        """Binds metrics buffers, shared memory references, and instantiates dirty arrays."""

        self.manager: AgentManager = manager
        self.set_proc_sc = manager.set_proc_sc

        cfgFP = manager.cfgFootprint
        self.space_flag: memoryview = cfgFP.space_flag
        self.spare_flag: memoryview = cfgFP.spare_flag
        self.base_nPrice: memoryview = cfgFP.base_price.cast("q")
        self.base_timestamp: memoryview = cfgFP.base_timestamp.cast("q")
        self.save_fp_headers: bool = cfgFP.save_fp_headers
        self.idxVP, self.idxDP = cfgFP.colVP, cfgFP.colDP

        cfgMetrics = manager.cfgMetrics
        self.time_start_reading: memoryview = cfgMetrics.time_start_reading.cast("q")

        self._init_array()

        self.con: FPconverter = FPconverter(
            footprint=self.footprint,
            headers=self.headers,
            cfgCoin=manager.cfgCoin,
            cfgFP=cfgFP,
        )
        self.last_idx: memoryview = memoryview(bytearray(8)).cast("q")
        self.counterTicks: memoryview = memoryview(bytearray(8)).cast("Q")
        self.defaultSpace: list[int] = [self.con.fp_rows, self.con.fp_cols, 0, 0]
        self.base_fp_dump_path: str = (
            f"{c.BASE_FOOTPRINT_DUMP_PATH}/{manager.cfgCoin.symbol.upper()}"
        )

        self.has_pre_trade: bool = False
        self._pre_price: float = 0.0
        self._pre_qty: float = 0.0
        self._pre_timestamp: int = 0
        self._pre_is_sell: bool = False

    def _init_array(self) -> None:
        """Initializes NumPy array abstractions over shared memory buffers and local dirty arrays."""

        cfgFP = self.manager.cfgFootprint
        self.footprint: NDArray[int64] = np.ndarray(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols),
            dtype=int64,
            buffer=cfgFP.footprint,
        )
        self.dirty_footprint: NDArray[int64] = np.ndarray(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols), dtype=int64
        )

        self.meta_data: NDArray[float64] = np.ndarray(
            shape=(2, BHM_ConstantCount), dtype=float64, buffer=cfgFP.metadata
        )

        self.headers: NDArray[int64] = np.ndarray(
            shape=(cfgFP.bar_count, c.BH_ConstantCount),
            dtype=int64,
            buffer=cfgFP.headers,
        )
        self.dirty_headers: NDArray[int64] = np.ndarray(
            shape=(cfgFP.bar_count, c.BH_ConstantCount), dtype=int64
        )

        self.space: NDArray[int64] = np.ndarray(
            shape=(2, SpaceCoords._ConstantCount), dtype=int64, buffer=cfgFP.space
        )

    def init_session(self, price: float, timestamp: int) -> None:
        """Resets arrays and calibrates layout converter for a new trading session."""
        self.dirty_footprint.fill(0)
        self.dirty_headers.fill(0)
        self.footprint.fill(0)
        self.headers.fill(0)
        self.meta_data.fill(0)
        self.last_idx[0] = 0
        self.space[:] = self.defaultSpace

        self.con.init_session(
            (self._pre_price if self.has_pre_trade else price),
            (self._pre_timestamp if self.has_pre_trade else timestamp),
        )

        self.base_nPrice[0] = self.con.nBasePrice
        self.base_timestamp[0] = self.con.baseTimestamp

    def update_footprint(
        self, price: float, qty: float, timestamp: int, is_sell: bool
    ) -> bool:
        """Ingests tick data, updates dirty structures, and triggers double-buffer flush.

        Returns:
            bool: True if dirty updates were successfully copied to primary shared memory buffer.
        """

        if self.has_pre_trade:
            pre_price, pre_qty, pre_timestamp, pre_is_sell = self.pre_trade
            self.update(pre_price, pre_qty, pre_timestamp, pre_is_sell)

        self.update(price, qty, timestamp, is_sell)

        return self.copy_to()

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> None:
        nPrice: int = self.con.to_nPrice(price)
        idy: int | None = self.con.to_idy(nPrice=nPrice)
        idx: int | None = self.con.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.last_idx[0] = idx
                self.update_footprint_and_headers_and_indicators_and_coords(
                    price=price,
                    qty=qty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                    nPrice=nPrice,
                    idy=idy,
                    idx=idx,
                )
            else:
                self.set_proc_sc(code=scs.FP_IDY_FILLED)
                self.pre_trade = price, qty, timestamp, is_sell

        else:
            self.wait_read_space()
            self.set_proc_sc(code=scs.FP_IDX_FILLED)
            self.pre_trade = price, qty, timestamp, is_sell

        self.counterTicks[0] += 1

    @property
    def pre_trade(self) -> tuple[float, float, int, bool]:
        _ = self
        _.has_pre_trade = False
        trade = _._pre_price, _._pre_qty, _._pre_timestamp, _._pre_is_sell
        _._pre_price, _._pre_qty, _._pre_timestamp, _._pre_is_sell = 0, 0, 0, True
        return trade

    @pre_trade.setter
    def pre_trade(self, trade: tuple[float, float, int, bool]) -> None:
        self._pre_price, self._pre_qty, self._pre_timestamp, self._pre_is_sell = trade
        self.has_pre_trade = True

    def update_footprint_and_headers_and_indicators_and_coords(
        self,
        price: float,
        qty: float,
        timestamp: int,
        is_sell: bool,
        nPrice: int,
        idy: int,
        idx: int,
    ) -> None:
        """Dispatches tick parameter tuple to Numba JIT calculation kernel."""

        _update_footprint_and_headers_and_indicators_and_coords(
            price=price,
            qty=qty,
            timestamp=timestamp,
            is_sell=is_sell,
            nPrice=nPrice,
            idy=idy,
            idx=idx,
            idxVP=self.idxVP,
            idxDP=self.idxDP,
            price_mult=self.con.price_mult,
            qty_mult=self.con.qty_mult,
            dirty_fp=self.dirty_footprint,
            dirty_hr=self.dirty_headers,
            space=self.space,
            space_flag=self.space_flag,
            meta_data=self.meta_data,
        )

    def wait_read_space(self) -> None:
        """Blocks until reader process releases spare buffer lock."""

        while self.spare_flag[0] == 1:
            time.sleep(0)

    def copy_to(self) -> bool:
        """Flushes local dirty array updates to active shared memory buffer when spare flag is clear."""

        if self.spare_flag[0] == 0:
            _copy_to(
                idxVP=self.idxVP,
                fp=self.footprint,
                dirty_fp=self.dirty_footprint,
                hr=self.headers,
                dirty_hr=self.dirty_headers,
                space=self.space,
                space_flag=self.space_flag,
            )
            self.time_start_reading[0] = time.perf_counter_ns()
            self.spare_flag[0] = 1
            return True
        return False

    # For Agent Method's
    def save_fp_headers_array(self) -> None:
        """Persists current bar headers array to local disk storage."""

        if self.save_fp_headers:
            os.makedirs(self.base_fp_dump_path, exist_ok=True)
            headers_save_path = (
                f"{self.base_fp_dump_path}/{self.con.get_time(idx=0, strftime=True)}"
            )
            if not os.path.exists(headers_save_path):
                np.save(headers_save_path, self.headers)

    def pre_re_init(self) -> None:
        """Saves Footprint headers and emits re-initialization status code prior to grid reset."""

        self.wait_read_space()
        self.save_fp_headers_array()
        self.set_proc_sc(scs.FP_RE_INIT)

    def space_is_read(self) -> bool:
        """Checks if active modify bounding box matches default state."""

        return bool(np.all(self.space[:] == self.defaultSpace))

    def final_actions(self) -> None:
        """Flushes remaining Footprint headers to disk upon process completion."""

        if (self.last_idx[0] & ~1) == (self.manager.cfgFootprint.fp_cols - 1 & ~1):
            self.save_fp_headers_array()


@njit(cache=True)
def _update_footprint_and_headers_and_indicators_and_coords(
    price: float,
    qty: float,
    timestamp: int,
    is_sell: bool,
    nPrice: int,
    idy: int,
    idx: int,
    idxVP: int,
    idxDP: int,
    price_mult: int,
    qty_mult: int,
    dirty_fp: NDArray[int64],
    dirty_hr: NDArray[int64],
    space: NDArray[int64],
    space_flag: memoryview,
    meta_data: NDArray[float64],
) -> None:
    """Numba JIT kernel updating volume profile, bar headers, VWAP, BB, and space coordinates."""

    nQty: int = round(qty * qty_mult)
    # Update Dirty Footprint
    dirty_fp[idy, idx] += nQty
    dirty_fp[idy, idxVP] += nQty  # VolumeProfile
    dirty_fp[idy, idxDP] += -nQty if is_sell else nQty  # Delta Profile
    # Update Dirty BarHeaders
    bar: int = (idx & ~1) // 2
    if dirty_hr[bar, c.BH_CountTrade] == 0:  # Init Bar
        dirty_hr[bar, c.BH_Open : c.BH_Close + 1] = nPrice
        dirty_hr[bar, c.BH_Time] = timestamp

    if nPrice > dirty_hr[bar, c.BH_High]:
        dirty_hr[bar, c.BH_High] = nPrice
    if nPrice < dirty_hr[bar, c.BH_Low]:
        dirty_hr[bar, c.BH_Low] = nPrice

    dirty_hr[bar, c.BH_Close] = nPrice
    dirty_hr[bar, c.BH_LastTradeTime] = timestamp

    dirty_hr[bar, c.BH_CountTrade] += 1
    dirty_hr[bar, c.BH_Volume] += nQty
    dirty_hr[bar, c.BH_Delta] += -nQty if is_sell else nQty
    if bar > 0:
        oldBar: int = bar - 1
        dirty_hr[bar, c.BH_CVD] = dirty_hr[bar, c.BH_Delta] + dirty_hr[oldBar, c.BH_CVD]
    else:
        dirty_hr[bar, c.BH_CVD] = dirty_hr[bar, c.BH_Delta]

    meta_data[0, BHM_VWAP_W] += qty
    meta_data[0, BHM_VWAP_PW] += price * qty
    meta_data[0, BHM_VWAP_P2W] += (price**2) * qty
    vwap: float64 = meta_data[0, BHM_VWAP_PW] / meta_data[0, BHM_VWAP_W]
    variance = max(
        0.0, ((meta_data[0, BHM_VWAP_P2W] / meta_data[0, BHM_VWAP_W]) - (vwap**2))
    )
    vwsd = np.sqrt(variance)
    upper_band, lower_band = vwap + (2.0 * vwsd), vwap - (2.0 * vwsd)
    dirty_hr[bar, c.BH_VWAP] = round(vwap * price_mult)
    dirty_hr[bar, c.BH_VWAP_BB_LOWER] = round(lower_band * price_mult)
    dirty_hr[bar, c.BH_VWAP_BB_UPPER] = round(upper_band * price_mult)

    # Update Space Coords
    buf: int = space_flag[0]
    idYmin, idXmin, idYmax, idXmax = space[buf, :]
    idYmin: int | int64 = idy if idYmin > idy else idYmin
    idXmin: int | int64 = idx if idXmin > idx else idXmin
    idYmax: int | int64 = idy + 1 if idYmax <= idy else idYmax
    idXmax: int | int64 = idx + 1 if idXmax <= idx else idXmax
    space[buf, :] = idYmin, idXmin, idYmax, idXmax


@njit(cache=True)
def _copy_to(
    idxVP: int,
    fp: NDArray[int64],
    dirty_fp: NDArray[int64],
    hr: NDArray[int64],
    dirty_hr: NDArray[int64],
    space: NDArray[int64],
    space_flag: memoryview,
) -> None:
    """Numba JIT kernel performing targeted memory copy of modified regions into shared memory."""

    buf: int = space_flag[0]
    idYmin, idXmin, idYmax, idXmax = space[buf, :]

    idxMin, idxMax = (idXmin & ~1) // 2, ((idXmax - 1) & ~1) // 2 + 1
    fp[idYmin:idYmax, idXmin:idXmax] = dirty_fp[idYmin:idYmax, idXmin:idXmax]
    fp[idYmin:idYmax, idxVP:] = dirty_fp[idYmin:idYmax, idxVP:]
    hr[idxMin:idxMax, : c.BH_CountTrade + 1] = dirty_hr[
        idxMin:idxMax, : c.BH_CountTrade + 1
    ]

    space_flag[0] = 1 if (buf == 0) else 0
