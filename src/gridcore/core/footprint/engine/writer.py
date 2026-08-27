from abc import ABC
from typing import override

import numpy as np
from numba import njit
from numpy import float64, int64
from numpy.typing import NDArray

from ... import constant as c
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from .base import Base

(
    BHM_VWAP_W,
    BHM_VWAP_PW,
    BHM_VWAP_P2W,
    BHM_ConstantCount,
) = [v for v in range(4)]
(
    FU_idxVP,
    FU_idxDP,
    FU_price_mult,
    FU_price_prec,
    FU_qty_mult,
    FU_qty_prec,
    FU_ConstantCount,
) = [v for v in range(7)]


class Writer(Base, ABC):
    def __init__(self, manager: NodeManager) -> None:
        super().__init__(manager)

        self._counter_ticks: int = 0

        self.__args[FU_idxVP] = self.con.idxVP
        self.__args[FU_idxDP] = self.con.idxDP
        self.__args[FU_price_mult] = self.con.price_mult
        self.__args[FU_price_prec] = self.con.price_prec
        self.__args[FU_qty_mult] = self.con.qty_mult
        self.__args[FU_qty_prec] = self.con.qty_prec

    @override
    def _init_array(self) -> None:
        super()._init_array()

        self.__meta_data: NDArray[float64] = np.zeros(
            shape=(2, BHM_ConstantCount), dtype=float64
        )
        self.__args: NDArray[int64] = np.zeros(shape=(FU_ConstantCount,), dtype=int64)

    @override
    def _init_session(self, nPrice: int, timestamp: int) -> None:
        super()._init_session(nPrice, timestamp)

        self.__meta_data.fill(0)

    def _update_footprint(
        self, nPrice: int, nQty: int, timestamp: int, is_sell: int
    ) -> None:
        if self._re_init_session:
            self._init_session(nPrice, timestamp)

        self.__update(nPrice, nQty, timestamp, is_sell)

    def __update(self, nPrice: int, nQty: int, timestamp: int, is_sell: int) -> None:
        idy: int | None = self.con.to_idy(nPrice=nPrice)
        idx: int | None = self.con.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self._counter_ticks += 1
                _update(
                    nPrice=nPrice,
                    nQty=nQty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                    idy=idy,
                    idx=idx,
                    args=self.__args,
                    footprint=self._footprint,
                    headers=self._headers,
                    bbox=self._bbox,
                    meta_data=self.__meta_data,
                )
            else:
                self._manager.set_proc_sc(code=scs.FP_IDY_FILLED, wait_main_task=False)
                if self.__bbox_is_read():
                    self._init_session(nPrice, timestamp)
                    self.__update(nPrice, nQty, timestamp, is_sell)
                else:
                    self._re_init_session: bool = True

        else:
            self._manager.set_proc_sc(code=scs.FP_IDX_FILLED, wait_main_task=False)
            if self.__bbox_is_read():
                self._init_session(nPrice, timestamp)
                self.__update(nPrice, nQty, timestamp, is_sell)
            else:
                self._re_init_session = True

    def __bbox_is_read(self) -> bool:
        return bool(np.all(self._bbox == self._bbox_default_value))


@njit(cache=True)
def _update(
    nPrice: int,
    nQty: int,
    timestamp: int,
    is_sell: int,
    idy: int,
    idx: int,
    args: NDArray[int64],
    footprint: NDArray[int64],
    headers: NDArray[int64],
    bbox: NDArray[int64],
    meta_data: NDArray[float64],
) -> None:
    idxVP, idxDP = args[FU_idxVP], args[FU_idxDP]
    price_mult, price_prec = args[FU_price_mult], args[FU_price_prec]
    qty_mult, qty_prec = args[FU_qty_mult], args[FU_qty_prec]
    # - - -

    # Update Footprint
    footprint[idy, idx] += nQty
    footprint[idy, idxVP] += nQty
    footprint[idy, idxDP] += -nQty if is_sell else nQty

    # Update Headers
    bar: int = (idx & ~1) // 2
    if headers[bar, c.BH_CountTrade] == 0:
        headers[bar, c.BH_Open : c.BH_Close + 1] = nPrice
        headers[bar, c.BH_Time] = timestamp

    if nPrice > headers[bar, c.BH_High]:
        headers[bar, c.BH_High] = nPrice
    if nPrice < headers[bar, c.BH_Low]:
        headers[bar, c.BH_Low] = nPrice

    headers[bar, c.BH_Close] = nPrice
    headers[bar, c.BH_LastTradeTime] = timestamp

    headers[bar, c.BH_CountTrade] += 1
    headers[bar, c.BH_Volume] += nQty
    headers[bar, c.BH_Delta] += -nQty if is_sell else nQty
    if bar > 0:
        oldBar: int = bar - 1
        headers[bar, c.BH_CVD] = headers[bar, c.BH_Delta] + headers[oldBar, c.BH_CVD]
    else:
        headers[bar, c.BH_CVD] = headers[bar, c.BH_Delta]

    price = round(nPrice / price_mult, price_prec)
    qty = round(nQty / qty_mult, qty_prec)

    meta_data[0, BHM_VWAP_W] += qty
    meta_data[0, BHM_VWAP_PW] += price * qty
    meta_data[0, BHM_VWAP_P2W] += (price**2) * qty
    vwap: float64 = meta_data[0, BHM_VWAP_PW] / meta_data[0, BHM_VWAP_W]
    variance = max(
        0.0, ((meta_data[0, BHM_VWAP_P2W] / meta_data[0, BHM_VWAP_W]) - (vwap**2))
    )
    vwsd = np.sqrt(variance)
    upper_band, lower_band = vwap + (2.0 * vwsd), vwap - (2.0 * vwsd)
    headers[bar, c.BH_VWAP] = round(vwap * price_mult)
    headers[bar, c.BH_VWAP_LOWER_BAND] = round(lower_band * price_mult)
    headers[bar, c.BH_VWAP_UPPER_BAND] = round(upper_band * price_mult)

    # Update BBOX
    idYmin, idXmin, idYmax, idXmax = bbox[:]
    idYmin: int | int64 = idy if idYmin > idy else idYmin
    idXmin: int | int64 = idx if idXmin > idx else idXmin
    idYmax: int | int64 = idy + 1 if idYmax <= idy else idYmax
    idXmax: int | int64 = idx + 1 if idXmax <= idx else idXmax
    bbox[:] = idYmin, idXmin, idYmax, idXmax
