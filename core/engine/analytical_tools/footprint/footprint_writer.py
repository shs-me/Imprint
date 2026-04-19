from multiprocessing.synchronize import Lock

import numpy as np
from numba import njit
from numpy.typing import NDArray

from .... import AgentManager
from .... import StatusCodes as sc
from ....settings import BarHeaders as chs
from ....settings import SpaceCoords as spc
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
        self.spcIDYmin, self.spcIDXmin = int(spc.IDYmin), int(spc.IDXmin)
        self.spcIDYmax, self.spcIDXmax = int(spc.IDYmax), int(spc.IDXmax)
        self.chsOpen, self.chsHigh = int(chs.Open), int(chs.High)
        self.chsLow, self.chsClose = int(chs.Low), int(chs.Close)
        self.chsVolume, self.chsDelta = int(chs.Volume), int(chs.Delta)
        self.chsTime, self.chsCountTrade = int(chs.Time), int(chs.CountTrade)
        self.chsCVD = int(chs.CVD)
        self.chsVWAP_P2Weights = int(chs.VWAP_P2Weights)
        self.chsVWAP_PWeights = int(chs.VWAP_PWeights)
        self.chsVWAP_Weights = int(chs.VWAP_Weights)

    def _init_array(self) -> None:
        self.footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.footprint)],
        )
        self.dirty_footprint: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.lines, self.cfgFootprint.panelCols),
            dtype=np.int64,
        )
        self.dirty_footprint.fill(0)
        # - - -
        self.headers: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.Bar_count, chs._HeadersCount),
            dtype=np.int64,
            buffer=self.manager.footprint_buf[slice(*self.cfgFootprint.headers)],
        )
        self.dirty_headers: NDArray[np.int64] = np.ndarray(
            shape=(self.cfgFootprint.Bar_count, chs._HeadersCount),
            dtype=np.int64,
        )
        self.dirty_headers.fill(0)
        # - - -
        self.space: NDArray[np.int64] = np.ndarray(
            (2, spc._CoordsCount),
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
            self.space[:, spc.IDYmin] = self.con.lines
            self.space[:, spc.IDXmin] = self.con.footprintCols
            self.space[:, spc.IDYmax :] = 0

        if self.con.init_session(price, timestamp) is False:
            self.set_status(code=sc.WARN2)
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
                    footprint=self.footprint,
                    dirty_footprint=self.dirty_footprint,
                    headers=self.headers,
                    dirty_headers=self.dirty_headers,
                    space=self.space,
                    space_flag=self.space_flag,
                    spare_flag=self.spare_flag,
                    spcIDYmin=self.spcIDYmin,
                    spcIDXmin=self.spcIDXmin,
                    spcIDYmax=self.spcIDYmax,
                    spcIDXmax=self.spcIDXmax,
                    chsOpen=self.chsOpen,
                    chsHigh=self.chsHigh,
                    chsLow=self.chsLow,
                    chsClose=self.chsClose,
                    chsVolume=self.chsVolume,
                    chsDelta=self.chsDelta,
                    chsTime=self.chsTime,
                    chsCountTrade=self.chsCountTrade,
                    chsCVD=self.chsCVD,
                    chsVWAP_P2Weights=self.chsVWAP_P2Weights,
                    chsVWAP_PWeights=self.chsVWAP_PWeights,
                    chsVWAP_Weights=self.chsVWAP_Weights,
                )

            else:
                self.set_status(code=sc.WARN4)
        else:
            self.set_status(code=sc.WARN3)

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
    footprint: NDArray[np.int64],
    dirty_footprint: NDArray[np.int64],
    headers: NDArray[np.int64],
    dirty_headers: NDArray[np.int64],
    space: NDArray[np.int64],
    space_flag: memoryview,
    spare_flag: memoryview,
    spcIDXmin: int,
    spcIDYmin: int,
    spcIDYmax: int,
    spcIDXmax: int,
    chsOpen: int,
    chsHigh: int,
    chsLow: int,
    chsClose: int,
    chsVolume: int,
    chsDelta: int,
    chsTime: int,
    chsCountTrade: int,
    chsCVD: int,
    chsVWAP_P2Weights: int,
    chsVWAP_PWeights: int,
    chsVWAP_Weights: int,
) -> bool:
    # Update Dirty Footprint
    dirty_footprint[idy, idx] += nQty
    dirty_footprint[idy, idxVP] += nQty  # VolumeProfile
    dirty_footprint[idy, idxDP] += -nQty if is_sell else nQty  # Delta Profile
    # Update Dirty Headers
    bar = (idx & ~1) // 2
    if dirty_headers[bar, chsCountTrade] == 0:  # Init Bar
        dirty_headers[bar, chsOpen : chsClose + 1] = idy
        dirty_headers[bar, chsTime] = timestamp

    if idy < dirty_headers[bar, chsHigh]:  # Update BarHigh: reverse
        dirty_headers[bar, chsHigh] = idy
    if idy > dirty_headers[bar, chsLow]:  # Update BarLow: reverse
        dirty_headers[bar, chsLow] = idy

    # Update Indicators
    dirty_headers[bar, chsClose] = idy
    dirty_headers[bar, chsCountTrade] += 1
    dirty_headers[bar, chsVolume] += nQty
    dirty_headers[bar, chsDelta] += -nQty if is_sell else nQty
    if bar > 0:
        oldCid = bar - 1
        dirty_headers[bar, chsCVD] = (
            dirty_headers[bar, chsDelta] + (dirty_headers[oldCid, chsCVD])
        )
        dirty_headers[bar, chsVWAP_P2Weights] = ((nPrice**2) * nQty) + dirty_headers[
            oldCid, chsVWAP_P2Weights
        ]
        dirty_headers[bar, chsVWAP_PWeights] = (nPrice * nQty) + dirty_headers[
            oldCid, chsVWAP_PWeights
        ]
        dirty_headers[bar, chsVWAP_Weights] = (
            nQty + (dirty_headers[oldCid, chsVWAP_Weights])
        )
    else:
        dirty_headers[bar, chsCVD] = dirty_headers[bar, chsDelta]
        dirty_headers[bar, chsVWAP_P2Weights] += (nPrice**2) * nQty
        dirty_headers[bar, chsVWAP_PWeights] += nPrice * nQty
        dirty_headers[bar, chsVWAP_Weights] += nQty

    # Update Space Coords
    buf: int = space_flag[0]
    new_buf: int = 1 if buf == 0 else 0
    space[buf, spcIDYmin] = IDYmin = (
        idy if space[buf, spcIDYmin] > idy else space[buf, spcIDYmin]
    )
    space[buf, spcIDXmin] = IDXmin = (
        idx if space[buf, spcIDXmin] > idx else space[buf, spcIDXmin]
    )
    space[buf, spcIDYmax] = IDYmax = (
        idy + 1 if space[buf, spcIDYmax] <= idy else space[buf, spcIDYmax]
    )
    space[buf, spcIDXmax] = IDXmax = (
        idx + 1 if space[buf, spcIDXmax] <= idx else space[buf, spcIDXmax]
    )

    # Change Buffer And Copy Values
    if spare_flag[0] == 0:
        idxMin, idxMax = (IDXmin & ~1) // 2, ((IDXmax - 1) & ~1) // 2 + 1
        headers[idxMin:idxMax, :] = dirty_headers[idxMin:idxMax, :]
        footprint[IDYmin:IDYmax, IDXmin:IDXmax] = dirty_footprint[
            IDYmin:IDYmax, IDXmin:IDXmax
        ]
        footprint[IDYmin:IDYmax, idxVP:] = dirty_footprint[IDYmin:IDYmax, idxVP:]
        space_flag[0], spare_flag[0] = new_buf, 1
        return True
    return False
