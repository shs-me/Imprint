from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import float64, int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.footprint.engine.base import Base
from imprint._core.footprint.models.converter import to_idx, to_idy

(
    BHM_VWAP_W,
    BHM_VWAP_PW,
    BHM_VWAP_P2W,
    BHM_ConstantCount,
) = [v for v in range(4)]
(
    FU_baseNprice,
    FU_center,
    FU_scale,
    FU_fp_rows,
    FU_baseTimestamp,
    FU_tims,
    FU_fp_cols,
    FU_idxVP,
    FU_idxDP,
    FU_price_mult,
    FU_price_prec,
    FU_qty_mult,
    FU_qty_prec,
    FU_ConstantCount,
) = [v for v in range(14)]


@dataclass(slots=True)
class Writer(Base, ABC):
    counter_ticks: int = field(default=0, init=False)

    __meta_data: NDArray[float64] = field(init=False)
    __args: NDArray[int64] = field(init=False)

    @override
    def child_init_array(self, nPrice: int64) -> None:
        if not (self.re_init & c.RIF_idy):
            self.__meta_data = np.zeros(
                shape=(2, BHM_ConstantCount), dtype=float64
            )
            self.__args = np.zeros(shape=(FU_ConstantCount,), dtype=int64)
            self.__args[FU_idxVP] = self.fp.con.idxVP
            self.__args[FU_idxDP] = self.fp.con.idxDP
            self.__args[FU_price_mult] = self.fp.con.price_mult
            self.__args[FU_price_prec] = self.fp.con.price_prec
            self.__args[FU_qty_mult] = self.fp.con.qty_mult
            self.__args[FU_qty_prec] = self.fp.con.qty_prec
            self.__args[FU_tims] = self.fp.con.tims
            self.__args[FU_fp_cols] = self.fp.con.fp_cols
            self.__args[FU_scale] = self.fp.con.scale

        else:
            self.__args[FU_center] = self.fp.con.center

        self.__args[FU_fp_rows] = self.fp.con.fp_rows

    @override
    def child_init_idx(self, nPrice: int64, timestamp: int64) -> None:
        self.__meta_data.fill(0)

        self.__args[FU_baseNprice] = self.fp.con.baseNprice
        self.__args[FU_baseTimestamp] = self.fp.con.baseTimestamp
        self.__args[FU_center] = self.fp.con.center

    @final
    def update_footprint(
        self, nPrice: int64, nQty: int64, timestamp: int64, is_sell: int64
    ) -> None:
        if self.re_init & (c.RIF_session):
            self.init_session(nPrice, timestamp)

        if result := _update(
            nPrice=nPrice,
            nQty=nQty,
            timestamp=timestamp,
            is_sell=is_sell,
            args=self.__args,
            footprint=self.fp.base,
            headers=self.fp.headers,
            headers_offset=self.fp.headers_offset,
            bbox=self.bbox,
            meta_data=self.__meta_data,
        ):
            self.re_init: int = result
        else:
            self.counter_ticks += 1


@njit(cache=True)
def _update(
    nPrice: int64,
    nQty: int64,
    timestamp: int64,
    is_sell: int64,
    args: NDArray[int64],
    footprint: NDArray[int64],
    headers: NDArray[int64],
    headers_offset: memoryview,
    bbox: NDArray[int64],
    meta_data: NDArray[float64],
) -> int | None:
    """
    Update footprint volume matrix, bar headers, VWAP statistics, and bounding box for a trade tick.

    Parameters
    ----------
    nPrice : int64
        Fixed-point price integer of incoming trade.
    nQty : int64
        Scaled fixed-point quantity integer of incoming trade.
    timestamp : int64
        Trade execution timestamp in milliseconds.
    is_sell : int64
        Trade direction flag (1 for sell/bid side, 0 for buy/ask side).
    args : NDArray[int64]
        1D array containing scaled constants, array index mappings, and converter configurations.
    footprint : NDArray[int64]
        2D footprint array storing volume profiles per price level and bar column.
    headers : NDArray[int64]
        2D array storing OHLCV, CVD, VWAP, and indicator metadata for each bar.
    headers_offset : memoryview
        Single-element int64 memory view maintaining active header buffer write offset.
    bbox : NDArray[int64]
        1D array of shape (4,) storing updated bounding box coordinates `[idYmin, idXmin, idYmax, idXmax]`.
    meta_data : NDArray[float64]
        2D array holding intermediate running metrics for VWAP calculation (volume, price*qty, price^2*qty).

    Returns
    -------
    int or None
        Bitmask integer containing re-initialization flags (`RIF_*`) if trade falls outside grid boundaries,
        or 0 (evaluating as falsy in caller context) when update succeeds.
    """
    re_init: int = 0

    idx: int64 = to_idx(
        timestamp=timestamp,
        is_sell=is_sell,
        baseTimestamp=args[FU_baseTimestamp],
        tims=args[FU_tims],
        fp_cols=args[FU_fp_cols],
    )
    if idx < 0:
        re_init |= c.RIF_session | c.RIF_idx
        return re_init

    idy: int64 = to_idy(
        nPrice=nPrice,
        baseNprice=args[FU_baseNprice],
        center=args[FU_center],
        scale=args[FU_scale],
        fp_rows=args[FU_fp_rows],
    )
    if idy < 0:
        re_init |= c.RIF_session | c.RIF_idy
        return re_init

    price_mult, price_prec = args[FU_price_mult], args[FU_price_prec]
    qty_mult, qty_prec = args[FU_qty_mult], args[FU_qty_prec]

    # Update Footprint
    footprint[idy, idx] += nQty
    footprint[idy, args[FU_idxVP]] += nQty
    footprint[idy, args[FU_idxDP]] += -nQty if is_sell else nQty

    # Update Headers
    bar: int64 = (idx & ~1) // 2
    bwo: int64 = headers_offset[0] + bar
    if headers[bwo, c.BH_CountTrade] == 0:
        headers[bwo, c.BH_Open : c.BH_Close + 1] = nPrice
        headers[bwo, c.BH_Time] = timestamp

    headers[bwo, c.BH_High] = max(nPrice, headers[bwo, c.BH_High])
    headers[bwo, c.BH_Low] = min(nPrice, headers[bwo, c.BH_Low])
    headers[bwo, c.BH_Close] = nPrice
    headers[bwo, c.BH_LastTradeTime] = timestamp

    headers[bwo, c.BH_CountTrade] += 1
    headers[bwo, c.BH_Volume] += nQty
    headers[bwo, c.BH_Delta] += -nQty if is_sell else nQty
    if bar > 0:
        headers[bwo, c.BH_CVD] = (
            headers[bwo, c.BH_Delta] + headers[bwo - 1, c.BH_CVD]
        )
    else:
        headers[bwo, c.BH_CVD] = headers[bwo, c.BH_Delta]

    price = round(nPrice / price_mult, price_prec)
    qty = round(nQty / qty_mult, qty_prec)

    meta_data[0, BHM_VWAP_W] += qty
    meta_data[0, BHM_VWAP_PW] += price * qty
    meta_data[0, BHM_VWAP_P2W] += (price**2) * qty
    vwap: float64 = meta_data[0, BHM_VWAP_PW] / meta_data[0, BHM_VWAP_W]
    variance = max(
        0.0,
        ((meta_data[0, BHM_VWAP_P2W] / meta_data[0, BHM_VWAP_W]) - (vwap**2)),
    )
    vwsd = np.sqrt(variance)
    upper_band, lower_band = vwap + (2.0 * vwsd), vwap - (2.0 * vwsd)
    headers[bwo, c.BH_VWAP] = round(vwap * price_mult)
    headers[bwo, c.BH_VWAP_LOWER_BAND] = round(lower_band * price_mult)
    headers[bwo, c.BH_VWAP_UPPER_BAND] = round(upper_band * price_mult)

    # Update BBOX
    idYmin, idXmin, idYmax, idXmax = bbox[:]
    idYmin: int | int64 = min(idYmin, idy)
    idXmin: int | int64 = min(idXmin, idx)
    idYmax: int | int64 = idy + 1 if idYmax <= idy else idYmax
    idXmax: int | int64 = idx + 1 if idXmax <= idx else idXmax
    bbox[:] = idYmin, idXmin, idYmax, idXmax
