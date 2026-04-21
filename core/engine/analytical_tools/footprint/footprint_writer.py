from multiprocessing.synchronize import Lock

import numpy as np
from numba import njit
from numpy.typing import NDArray

from .... import AgentManager
from .... import StatusCodes as stc
from ....settings import BarHeaders as bh
from ....settings import SpaceCoords as sc
from .. import ConvertMetrics


class FootprintWriter:
    def __init__(self, manager: AgentManager, guarantee: Lock) -> None:
        self.manager, self.guarantee = manager, guarantee
        self.set_status = manager.set_status
        self.mode = manager.cfgBacktesting.mode
        # Footprint
        self.cfgFootprint = self.manager.cfgFootprint
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
        self.idxVP, self.idxDP = self.cfgFootprint.colVP, self.cfgFootprint.colDP
        self.spcIDYmin, self.spcIDXmin = int(sc.IDYmin), int(sc.IDXmin)
        self.spcIDYmax, self.spcIDXmax = int(sc.IDYmax), int(sc.IDXmax)
        self.chsOpen, self.chsHigh = int(bh.Open), int(bh.High)
        self.chsLow, self.chsClose = int(bh.Low), int(bh.Close)
        self.chsVolume, self.chsDelta = int(bh.Volume), int(bh.Delta)
        self.chsTime, self.chsCountTrade = int(bh.Time), int(bh.CountTrade)
        self.chsCVD = int(bh.CVD)
        self.chsVWAP_P2W = int(bh.VWAP_P2W)
        self.chsVWAP_PW = int(bh.VWAP_PW)
        self.chsVWAP_W = int(bh.VWAP_W)

    def _init_array(self) -> None:
        self.footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.fpLines, self.cfgFootprint.fpPanelCols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint)],
        )
        self.dirty_footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.fpLines, self.cfgFootprint.fpPanelCols),
            dtype=np.int64,
        )
        self.dirty_footprint.fill(0)
        # - - -
        self.headers: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.bar_count, bh._HeadersCount),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.headers)],
        )
        self.dirty_headers: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.bar_count, bh._HeadersCount),
            dtype=np.int64,
        )
        self.dirty_headers.fill(0)
        # - - -
        self.space: NDArray[np.int64] = np.ndarray(
            (2, sc._CoordsCount),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.space)],
        )

    def init_session(self, price: float, timestamp: int) -> bool:
        bpat = self.base_price_and_timestamp_buf
        # - - -
        self.con: ConvertMetrics = ConvertMetrics(
            trade_param=self.trade_par,
            footprint=self.footprint,
            headers=self.headers,
            cfgFootprint=self.cfgFootprint,
        )
        if bpat[0] != 0:
            price, timestamp = bpat[:]
        else:
            self.space[:] = self.con.fpLines, self.con.fpCols, 0, 0

        if self.con.init_session(price, timestamp) is False:
            self.set_status(code=stc.WARN2)
            return False

        bpat[0], bpat[1] = self.con.nBasePrice, self.con.baseTimestamp
        return True

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        nQty, nPrice = self.con.to_nQty(qty), self.con.to_nPrice(price)
        idy: int | None = self.con.to_idy(nPrice=nPrice)
        idx: int | None = self.con.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                return update_footprint_and_headers_and_indicators_and_coords(
                    nPrice=nPrice,
                    nQty=nQty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                    idy=idy,
                    idx=idx,
                    idxVP=self.idxVP,
                    idxDP=self.idxDP,
                    fp=self.footprint,
                    dirty_fp=self.dirty_footprint,
                    hr=self.headers,
                    dirty_hr=self.dirty_headers,
                    space=self.space,
                    space_flag=self.space_flag,
                    spare_flag=self.spare_flag,
                    chsOpen=self.chsOpen,
                    chsHigh=self.chsHigh,
                    chsLow=self.chsLow,
                    chsClose=self.chsClose,
                    chsVolume=self.chsVolume,
                    chsDelta=self.chsDelta,
                    chsTime=self.chsTime,
                    chsCountTrade=self.chsCountTrade,
                    chsCVD=self.chsCVD,
                    chsVWAP_P2W=self.chsVWAP_P2W,
                    chsVWAP_PW=self.chsVWAP_PW,
                    chsVWAP_W=self.chsVWAP_W,
                )

            else:
                self.set_status(code=stc.WARN4)
        else:
            self.set_status(code=stc.WARN3)

        return False


@njit(cache=True)
def update_footprint_and_headers_and_indicators_and_coords(
    nPrice: int,
    nQty: int,
    timestamp: int,
    is_sell: bool,
    idy: int,
    idx: int,
    idxVP: int,
    idxDP: int,
    fp: NDArray[np.int64],
    dirty_fp: NDArray[np.int64],
    hr: NDArray[np.int64],
    dirty_hr: NDArray[np.int64],
    space: NDArray[np.int64],
    space_flag: memoryview,
    spare_flag: memoryview,
    chsOpen: int,
    chsHigh: int,
    chsLow: int,
    chsClose: int,
    chsVolume: int,
    chsDelta: int,
    chsTime: int,
    chsCountTrade: int,
    chsCVD: int,
    chsVWAP_P2W: int,
    chsVWAP_PW: int,
    chsVWAP_W: int,
) -> bool:
    # Update Dirty Footprint
    dirty_fp[idy, idx] += nQty
    dirty_fp[idy, idxVP] += nQty  # VolumeProfile
    dirty_fp[idy, idxDP] += -nQty if is_sell else nQty  # Delta Profile

    # Update Dirty Headers
    # Headers: OHLC
    bar = (idx & ~1) // 2
    if dirty_hr[bar, chsCountTrade] == 0:  # Init Bar
        dirty_hr[bar, chsOpen : chsClose + 1] = idy
        dirty_hr[bar, chsTime] = timestamp

    if idy < dirty_hr[bar, chsHigh]:  # Update BarHigh: reverse
        dirty_hr[bar, chsHigh] = idy
    if idy > dirty_hr[bar, chsLow]:  # Update BarLow: reverse
        dirty_hr[bar, chsLow] = idy

    dirty_hr[bar, chsClose] = idy
    # Headers: Update Indicators
    dirty_hr[bar, chsCountTrade] += 1
    dirty_hr[bar, chsVolume] += nQty
    dirty_hr[bar, chsDelta] += -nQty if is_sell else nQty
    if bar > 0:
        oldBar = bar - 1
        dirty_hr[bar, chsCVD] = dirty_hr[bar, chsDelta] + (dirty_hr[oldBar, chsCVD])
        dirty_hr[bar, chsVWAP_P2W] = ((nPrice**2) * nQty) + dirty_hr[
            oldBar, chsVWAP_P2W
        ]
        dirty_hr[bar, chsVWAP_PW] = (nPrice * nQty) + dirty_hr[oldBar, chsVWAP_PW]
        dirty_hr[bar, chsVWAP_W] = nQty + (dirty_hr[oldBar, chsVWAP_W])
    else:
        dirty_hr[bar, chsCVD] = dirty_hr[bar, chsDelta]
        dirty_hr[bar, chsVWAP_P2W] += (nPrice**2) * nQty
        dirty_hr[bar, chsVWAP_PW] += nPrice * nQty
        dirty_hr[bar, chsVWAP_W] += nQty

    # Update Space Coords
    buf: int = space_flag[0]
    IDYmin, IDXmin, IDYmax, IDXmax = space[buf, :]
    IDYmin: int | np.int64 = idy if IDYmin > idy else IDYmin
    IDXmin: int | np.int64 = idx if IDXmin > idx else IDXmin
    IDYmax: int | np.int64 = idy + 1 if IDYmax <= idy else IDYmax
    IDXmax: int | np.int64 = idx + 1 if IDXmax <= idx else IDXmax
    space[buf, :] = IDYmin, IDXmin, IDYmax, IDXmax

    # IF True: Change buffer and copy value's to pure array's
    if spare_flag[0] == 0:
        idxMin, idxMax = (IDXmin & ~1) // 2, ((IDXmax - 1) & ~1) // 2 + 1
        hr[idxMin:idxMax, :] = dirty_hr[idxMin:idxMax, :]
        fp[IDYmin:IDYmax, IDXmin:IDXmax] = dirty_fp[IDYmin:IDYmax, IDXmin:IDXmax]
        fp[IDYmin:IDYmax, idxVP:] = dirty_fp[IDYmin:IDYmax, idxVP:]
        space_flag[0], spare_flag[0] = 1 if buf == 0 else 0, 1
        return True

    return False
