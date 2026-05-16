import numpy as np
from numba import njit
from numpy import int64, object_
from numpy.typing import NDArray

from core import constant as c
from core.engine.agents_utils.execution.trade_manager import TradeManager
from core.engine.agents_utils.utils import TradeConverter
from core.utils.monitoring.agent_manager import AgentManager


class MatchingEngine:
    def __init__(
        self, manager: AgentManager, con: TradeConverter, tm: TradeManager
    ) -> None:
        self.manager: AgentManager = manager
        self.con: TradeConverter = con
        self.tm: TradeManager = tm
        # Footprint
        self.cfgFootprint = self.manager.cfgFootprint
        self.space_flag: memoryview[int] = self.manager.footprint_buf[
            self.cfgFootprint.flag : self.cfgFootprint.flag + 1
        ]
        # Strategy
        self.cfgStrategy = self.manager.cfgStrategy
        self.tradesLines: int = self.cfgStrategy.tradesLines
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.dfmLines: int = self.cfgMetrics.dfmLines
        self.dfm_1RID: memoryview = self.manager.metrics_buf[
            slice(*self.cfgMetrics.dfm_1_row_id)
        ].cast("q")
        self.dfm_2RID: memoryview = self.manager.metrics_buf[
            slice(*self.cfgMetrics.dfm_2_row_id)
        ].cast("q")
        self.timeStartReading: memoryview = self.manager.metrics_buf[
            slice(*self.cfgMetrics.timeStartReading)
        ].cast("q")
        # Variable's
        self.dfm_RRid: memoryview = memoryview(bytearray(8)).cast("q")
        self._init_array()

    def _init_array(self) -> None:
        self.dfm_1: NDArray[int64] = np.ndarray(
            shape=(self.cfgMetrics.dfmLines, self.cfgMetrics.dfmCols),
            dtype=int64,
            buffer=self.manager.metrics_buf[slice(*self.cfgMetrics.dfm_1)],
        )
        self.dfm_2: NDArray[int64] = np.ndarray(
            shape=(self.cfgMetrics.dfmLines, self.cfgMetrics.dfmCols),
            dtype=int64,
            buffer=self.manager.metrics_buf[slice(*self.cfgMetrics.dfm_2)],
        )

    @property
    def dfm(self) -> NDArray[int64]:
        return self.dfm_2 if (self.space_flag[0] == 0) else self.dfm_1

    @property
    def dfmRID(self) -> memoryview:
        return self.dfm_2RID if (self.space_flag[0] == 0) else self.dfm_1RID

    def find_market_order_data(self, timestamp: int) -> tuple[int, int] | None:
        return _binary_search(
            dfm=self.dfm,
            timestamp=timestamp,
            high=self.dfmRID[0] - 1,
            low=self.dfm_RRid[0],
        )

    def execute_market_order(
        self, fpNprice: int, nQty: int, timestamp: int, is_long: bool, is_buy: bool
    ) -> int:
        _ = self.con
        # - - -
        nPrice: int = _.to_nPrice(_.to_fpPrice(fpNprice))
        slipageTicks: int = nPrice * _.slipage // 10000
        nPrice = nPrice + (slipageTicks if is_buy else -slipageTicks)
        nCommission: int = nQty * _.takerNcommission // 10000

        orderParam: int = 0
        orderParam |= c.OF_LONG if is_long else c.OF_SHORT
        orderParam |= c.OF_BUY if is_buy else c.OF_SELL
        orderParam |= c.OF_MARKET
        orderParam |= c.OF_FILLED

        self.tm.update_orders_array(
            nPrice, nQty, timestamp, orderParam, nCommission, orderID=None
        )
        return nPrice

    def execute_limit_orders(self, highWrow: int | None = None) -> None:
        _execute_limit_orders(
            dfm=self.dfm,
            dfm_nRID=self.dfm_RRid,
            active_orders=self.tm.active_orders,
            orders_history=self.tm.orders_history,
            ohWRow=self.tm.ohWRow,
            aoWRow=self.tm.aoWRow,
            takerNcommission=self.con.takerNcommission,
            makerNcommission=self.con.makerNcommission,
            slipage=self.con.slipage,
            scale=self.con.scale,
            priceMult=self.con.priceMult,
            pricePrec=self.con.pricePrec,
            highWrow=highWrow if (highWrow is not None) else self.dfmRID[0],
        )


def _execute_limit_orders(
    dfm: NDArray[int64],
    dfm_nRID: memoryview,
    active_orders: NDArray[object_],
    orders_history: NDArray[object_],
    ohWRow: memoryview,
    aoWRow: memoryview,
    takerNcommission: int,
    makerNcommission: int,
    slipage: int,
    scale: int,
    priceMult: float,
    pricePrec: int,
    highWrow: int,
) -> None:
    rRow, wRow = dfm_nRID[0], highWrow
    if rRow >= wRow:
        return

    if aoWRow[0] == 0:
        dfm_nRID[0] = wRow

    _nPrice, _nQty, _timestamp, _orderParam, _nCom, _orderID = 0, 0, 0, 0, 0, 0
    oh, ao = orders_history, active_orders
    # - - -
    for _row in range(rRow, wRow):
        nPrice: int = round(
            round((dfm[_row, c.DFM_nPrice] / priceMult), pricePrec) * scale
        )
        startTimestamp: int64 = dfm[_row, c.DFM_startTimestamp]
        endTimestamp: int64 = dfm[_row, c.DFM_endTimestamp]

        aoWrow: int = aoWRow[0]
        _diff_for_row: int = 0
        for aoRow in range(aoWrow):
            if aoWRow[0] == 0:
                dfm_nRID[0] = wRow
                return

            executed, cancelSL = False, True
            aoRow = aoRow - _diff_for_row

            tpNprice: int = ao[aoRow, c.AO_nPrice, 0]
            tpNqty: int = ao[aoRow, c.AO_nQty, 0]
            tpOrderParam: int = ao[aoRow, c.AO_orderParam, 0]
            tpOrderID: int = ao[aoRow, c.AO_orderID, 0]
            tpIsBuy: bool = bool(tpOrderParam & c.OF_BUY)

            slNprice: int = ao[aoRow, c.AO_nPrice, 1]
            slNqty: int = ao[aoRow, c.AO_nQty, 1]
            slOrderParam: int = ao[aoRow, c.AO_orderParam, 1]
            slOrderID: int = ao[aoRow, c.AO_orderID, 1]
            slIsBuy: bool = bool(slOrderParam & c.OF_BUY)

            if (tpIsBuy and (nPrice <= tpNprice)) or (
                not tpIsBuy and (nPrice >= tpNprice)
            ):
                _nPrice, _nQty, _timestamp = tpNprice, tpNqty, int(startTimestamp)
                _orderParam, _orderID = tpOrderParam, tpOrderID
                _nCom = tpNqty * makerNcommission // 1000

                executed, cancelSL = True, True

            elif (slIsBuy and (nPrice >= slNprice)) or (
                not slIsBuy and (nPrice <= slNprice)
            ):
                slipageTicks = nPrice * slipage // 10000
                _nPrice = nPrice + (slipageTicks if slIsBuy else -slipageTicks)
                _nQty, _timestamp = slNqty, int(endTimestamp)
                _orderParam, _orderID = slOrderParam, slOrderID
                _nCom = slNqty * takerNcommission // 1000

                executed, cancelSL = True, False

            if executed:
                _orderParam &= ~(c.OF_NEW)
                _orderParam |= c.OF_FILLED

                ohRow = ohWRow[0]
                oh[ohRow, :] = _nPrice, _nQty, _timestamp, _orderParam, _nCom, _orderID
                ohWRow[0] += 1

                _orderParam_ = slOrderParam if cancelSL else tpOrderParam
                _orderParam_ &= ~(c.OF_NEW)
                _orderParam_ |= c.OF_CANCELED

                ohRow = ohWRow[0]
                oh[ohRow, c.TP_nPrice] = slNprice if cancelSL else tpNprice
                oh[ohRow, c.TP_nQty] = slNqty if cancelSL else tpNqty
                oh[ohRow, c.TP_timestamp] = _timestamp
                oh[ohRow, c.TP_orderParam] = _orderParam_
                oh[ohRow, c.TP_commission] = None
                oh[ohRow, c.TP_orderID] = slOrderID if cancelSL else tpOrderID
                ohWRow[0] += 1

                if ((aoWrow - 1) - aoRow) > 0:
                    ao[aoRow : aoWrow - 1, :, :] = ao[aoRow + 1 : aoWrow, :, :]
                    ao[aoWrow - 1, :, :] = None
                else:
                    ao[aoRow, :, :] = None

                aoWRow[0] -= 1
                _diff_for_row += 1

        dfm_nRID[0] += 1


@njit(cache=True)
def _binary_search(
    dfm: NDArray[int64], timestamp: int, high: int, low: int = 0
) -> tuple[int, int] | None:
    max_idx = high
    while low <= high:
        mid: int = (low + high) // 2
        startTimestamp: int = dfm[mid, c.DFM_startTimestamp]
        endTimestamp: int = dfm[mid, c.DFM_endTimestamp]
        if startTimestamp <= timestamp <= endTimestamp:
            return dfm[mid, c.DFM_nPrice], mid
        elif timestamp < endTimestamp:
            high = mid - 1
        else:
            low = mid + 1

    return (dfm[low, c.DFM_nPrice], low) if (low <= max_idx) else None
