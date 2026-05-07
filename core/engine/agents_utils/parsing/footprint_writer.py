import os
import time
from math import sqrt

import numpy as np
from numba import njit
from numpy import float64, int64
from numpy.typing import NDArray

from core.constant import BASE_FOOTPRINT_DUMP_PATH
from core.engine.agents_utils.utils import FPconverter
from core.settings import BarHeaders, SpaceCoords
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.status_codes import StatusCodes as scs

# Numba Constant
BarHeader_Open: int = int(BarHeaders.Open)
BarHeader_High: int = int(BarHeaders.High)
BarHeader_Low: int = int(BarHeaders.Low)
BarHeader_Close: int = int(BarHeaders.Close)
BarHeader_Volume: int = int(BarHeaders.Volume)
BarHeader_Delta: int = int(BarHeaders.Delta)
BarHeader_CVD: int = int(BarHeaders.CVD)
BarHeader_VWAP: int = int(BarHeaders.VWAP)
BarHeader_VWAP_BB_UPPER: int = int(BarHeaders.VWAP_BB_UPPER)
BarHeader_VWAP_BB_LOWER: int = int(BarHeaders.VWAP_BB_LOWER)
BarHeader_Time: int = int(BarHeaders.OpenTime)
BarHeader_LastTradeTime: int = int(BarHeaders.LastTradeTime)
BarHeader_CountTrade: int = int(BarHeaders.CountTrade)
BarHeader_HeadersCount: int = int(BarHeaders._HeadersCount)
# - - -


class FootprintWriter:
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager
        self.set_proc_sc = manager.set_proc_sc
        self.task_status = manager.task_status
        # Footprint
        self.cfgFootprint = self.manager.cfgFootprint
        self.save_headers: bool = self.cfgFootprint.save_headers
        self.space_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.flag : self.cfgFootprint.flag + 1
        ]
        self.spare_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.spare_flag : self.cfgFootprint.spare_flag + 1
        ]
        self.base_price_and_timestamp_buf: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.basePrice[0] : self.cfgFootprint.baseTimestamp[1]
        ].cast("q")
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self._init_array()
        # Variables
        self.base_fp_dump_path: str = (
            f"{BASE_FOOTPRINT_DUMP_PATH}/{self.manager.symbol.upper()}"
        )
        self.idxVP, self.idxDP = self.cfgFootprint.colVP, self.cfgFootprint.colDP
        self.con: FPconverter = FPconverter(
            footprint=self.footprint,
            headers=self.headers,
            trade_param=self.trade_par,
            cfgFP=self.cfgFootprint,
        )
        self.last_idx: memoryview = memoryview(bytearray(8)).cast("q")
        self.defaultSpace: list[int] = [self.con.fpLines, self.con.fpCols, 0, 0]

    def _init_array(self) -> None:
        self.footprint: NDArray[int64] = np.ndarray(
            shape=(self.cfgFootprint.fpLines, self.cfgFootprint.fpPanelCols),
            dtype=int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint)],
        )
        self.dirty_footprint: NDArray[int64] = np.ndarray(
            shape=(self.cfgFootprint.fpLines, self.cfgFootprint.fpPanelCols),
            dtype=int64,
        )
        # - - -
        self.meta_data: NDArray[float64] = np.ndarray(
            shape=(2, 3),
            dtype=float64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.meta_data)],
        )
        # - - -
        self.headers: NDArray[int64] = np.ndarray(
            shape=(self.cfgFootprint.bar_count, BarHeader_HeadersCount),
            dtype=int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.headers)],
        )
        self.dirty_headers: NDArray[int64] = np.ndarray(
            shape=(self.cfgFootprint.bar_count, BarHeader_HeadersCount),
            dtype=int64,
        )
        # - - -
        self.space: NDArray[int64] = np.ndarray(
            (2, SpaceCoords._CoordsCount),
            dtype=int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.space)],
        )

    def init_session(self, price: float, timestamp: int) -> bool:
        self.dirty_footprint.fill(0)
        self.dirty_headers.fill(0)
        self.footprint.fill(0)
        self.headers.fill(0)
        self.meta_data.fill(0)
        self.last_idx[0] = 0
        self.space[:] = self.defaultSpace

        self.con.init_session(price, timestamp)

        self.base_price_and_timestamp_buf[0] = self.con.nBasePrice
        self.base_price_and_timestamp_buf[1] = self.con.baseTimestamp
        return True

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        nPrice: int = self.con.to_nPrice(price)
        idy: int | None = self.con.to_idy(nPrice=nPrice)
        idx: int | None = self.con.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.last_idx[0] = idx
                update_footprint_and_headers_and_indicators_and_coords(
                    price=price,
                    qty=qty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                    nPrice=nPrice,
                    idy=idy,
                    idx=idx,
                    idxVP=self.idxVP,
                    idxDP=self.idxDP,
                    priceMult=self.con.priceMult,
                    qtyMult=self.con.qtyMult,
                    dirty_fp=self.dirty_footprint,
                    dirty_hr=self.dirty_headers,
                    space=self.space,
                    space_flag=self.space_flag,
                    meta_data=self.meta_data,
                )

            else:
                self.set_proc_sc(code=scs.FP_IDY_FILLED)

        else:
            self.wait_read_space()
            self.set_proc_sc(code=scs.FP_IDX_FILLED)

        return self._copy_to()

    def wait_read_space(self) -> None:
        while self.spare_flag[0] != 0:
            time.sleep(0.000001)

    def _copy_to(self) -> bool:
        return copy_to(
            idxVP=self.idxVP,
            fp=self.footprint,
            dirty_fp=self.dirty_footprint,
            hr=self.headers,
            dirty_hr=self.dirty_headers,
            space=self.space,
            space_flag=self.space_flag,
            spare_flag=self.spare_flag,
        )

    # For Agent Method's
    def save_headersArray(self) -> None:
        if self.save_headers:
            os.makedirs(self.base_fp_dump_path, exist_ok=True)
            headers_save_path = (
                f"{self.base_fp_dump_path}/{self.con.get_time(idx=0, strftime=True)}"
            )
            np.save(headers_save_path, self.headers)

    def pre_re_init(self) -> None:
        self.wait_read_space()
        self.save_headersArray()
        self.set_proc_sc(scs.FP_RE_INIT)

    def space_is_read(self) -> bool:
        return bool(np.all(self.space[:] == self.defaultSpace))

    def final_actions(self) -> None:
        if (self.last_idx[0] & ~1) == (self.cfgFootprint.fpCols - 1 & ~1):
            self.save_headersArray()


@njit(cache=True)
def update_footprint_and_headers_and_indicators_and_coords(
    price: float,
    qty: float,
    timestamp: int,
    is_sell: bool,
    nPrice: int,
    idy: int,
    idx: int,
    idxVP: int,
    idxDP: int,
    priceMult: float,
    qtyMult: float,
    dirty_fp: NDArray[int64],
    dirty_hr: NDArray[int64],
    space: NDArray[int64],
    space_flag: memoryview,
    meta_data: NDArray[np.float64],
) -> None:
    nQty: int = round(qty * qtyMult)
    # Update Dirty Footprint
    dirty_fp[idy, idx] += nQty
    dirty_fp[idy, idxVP] += nQty  # VolumeProfile
    dirty_fp[idy, idxDP] += -nQty if is_sell else nQty  # Delta Profile
    # Update Dirty BarHeader_s
    bar: int = (idx & ~1) // 2
    # BarHeader_s: OHLC
    if dirty_hr[bar, BarHeader_CountTrade] == 0:  # Init Bar
        dirty_hr[bar, BarHeader_Open : BarHeader_Close + 1] = nPrice
        dirty_hr[bar, BarHeader_Time] = timestamp

    if nPrice > dirty_hr[bar, BarHeader_High]:
        dirty_hr[bar, BarHeader_High] = nPrice
    if nPrice < dirty_hr[bar, BarHeader_Low]:
        dirty_hr[bar, BarHeader_Low] = nPrice

    dirty_hr[bar, BarHeader_Close] = nPrice
    dirty_hr[bar, BarHeader_LastTradeTime] = timestamp
    # BarHeader_s: Update Indicators
    dirty_hr[bar, BarHeader_CountTrade] += 1
    dirty_hr[bar, BarHeader_Volume] += nQty
    dirty_hr[bar, BarHeader_Delta] += -nQty if is_sell else nQty
    if bar != 0:
        oldBar: int = bar - 1
        dirty_hr[bar, BarHeader_CVD] = (
            dirty_hr[bar, BarHeader_Delta] + dirty_hr[oldBar, BarHeader_CVD]
        )
    else:
        dirty_hr[bar, BarHeader_CVD] = dirty_hr[bar, BarHeader_Delta]

    meta_data[0, 0] += qty
    meta_data[0, 1] += price * qty
    meta_data[0, 2] += price**2 * qty
    vwap: float64 = meta_data[0, 1] / meta_data[0, 0]
    std_dev: float = sqrt(max(0.0, (meta_data[0, 2] / meta_data[0, 0]) - (vwap**2)))
    upper_bb, lower_bb = vwap + (2 * std_dev), vwap - (2 * std_dev)
    dirty_hr[bar, BarHeader_VWAP] = round(vwap * priceMult)
    dirty_hr[bar, BarHeader_VWAP_BB_LOWER] = round(lower_bb * priceMult)
    dirty_hr[bar, BarHeader_VWAP_BB_UPPER] = round(upper_bb * priceMult)

    # Update Space Coords
    buf: int = space_flag[0]
    IDYmin, IDXmin, IDYmax, IDXmax = space[buf, :]
    IDYmin: int | int64 = idy if IDYmin > idy else IDYmin
    IDXmin: int | int64 = idx if IDXmin > idx else IDXmin
    IDYmax: int | int64 = idy + 1 if IDYmax <= idy else IDYmax
    IDXmax: int | int64 = idx + 1 if IDXmax <= idx else IDXmax
    space[buf, :] = IDYmin, IDXmin, IDYmax, IDXmax


@njit(cache=True)
def copy_to(
    fp: NDArray[int64],
    dirty_fp: NDArray[int64],
    hr: NDArray[int64],
    dirty_hr: NDArray[int64],
    space: NDArray[int64],
    space_flag: memoryview,
    spare_flag: memoryview,
    idxVP: int,
) -> bool:
    if spare_flag[0] == 0:  # IF True: Change buffer and copy value's to pure array's
        buf: int = space_flag[0]
        IDYmin, IDXmin, IDYmax, IDXmax = space[buf, :]

        idxMin, idxMax = (IDXmin & ~1) // 2, ((IDXmax - 1) & ~1) // 2 + 1
        hr[idxMin:idxMax, :] = dirty_hr[idxMin:idxMax, :]

        fp[IDYmin:IDYmax, IDXmin:IDXmax] = dirty_fp[IDYmin:IDYmax, IDXmin:IDXmax]
        fp[IDYmin:IDYmax, idxVP:] = dirty_fp[IDYmin:IDYmax, idxVP:]

        space_flag[0], spare_flag[0] = (1 if (buf == 0) else 0), 1
        return True

    return False
