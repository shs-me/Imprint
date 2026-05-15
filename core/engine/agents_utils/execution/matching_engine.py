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
            dfm=self.dfm, timestamp=timestamp, high=self.dfmRID[0] - 1
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
        if self.tm.have_active_orders:
            _execute_limit_orders(
                dfm=self.dfm,
                dfmRID=self.dfmRID,
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
                highWrow=highWrow,
            )


def _execute_limit_orders(
    dfm: NDArray[int64],
    dfmRID: memoryview,
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
    highWrow: int | None,
) -> None:
    oh, ao = orders_history, active_orders
    wRow: int = highWrow if highWrow else dfmRID[0]
    rRow: int = dfm_nRID[0]
    if rRow >= wRow:
        return

    _nPrice, _nQty, _timestamp, _orderParam, _nCommission, _orderID = 0, 0, 0, 0, 0, 0
    for _row in range(rRow, wRow):
        nPrice: int = round(
            round((dfm[_row, c.DFM_nPrice] / priceMult), pricePrec) * scale
        )
        startTimestamp: int64 = dfm[_row, c.DFM_startTimestamp]
        endTimestamp: int64 = dfm[_row, c.DFM_endTimestamp]

        aoWrow: int = aoWRow[0]
        _diff_for_row: int = 0
        for aoRow in range(aoWrow):
            if not bool(np.any(active_orders[:aoWrow, 0])):
                return

            _executed = False
            _cancelSl = True

            aoRow = aoRow - _diff_for_row

            _tpNprice: int = ao[aoRow, c.AO_nPrice, 0]
            _tpNqty: int = ao[aoRow, c.AO_nQty, 0]
            _tpOrderParam: int = ao[aoRow, c.AO_orderParam, 0]
            _tpOrderID: int = ao[aoRow, c.AO_orderID, 0]
            _tpIsBuy: bool = bool(_tpOrderParam & c.OF_BUY)

            _slNprice: int = ao[aoRow, c.AO_nPrice, 1]
            _slNqty: int = ao[aoRow, c.AO_nQty, 1]
            _slOrderParam: int = ao[aoRow, c.AO_orderParam, 1]
            _slOrderID: int = ao[aoRow, c.AO_orderID, 1]
            _slIsBuy: bool = bool(_tpOrderParam & c.OF_BUY)

            if (_tpIsBuy and (nPrice <= _tpNprice)) or (
                not _tpIsBuy and (nPrice >= _tpNprice)
            ):
                _nPrice = _tpNprice
                _nCommission = _tpNqty * makerNcommission // 1000
                _timestamp = int(startTimestamp)
                _orderParam = _tpOrderParam
                _orderID = _tpOrderID
                _executed = True
                _cancelSL = True

            if (_slIsBuy and (nPrice >= _slNprice)) or (
                not _slIsBuy and (nPrice <= _slNprice)
            ):
                slipageTicks: int = nPrice * slipage // 10000
                _nPrice = nPrice + (slipageTicks if _slIsBuy else -slipageTicks)
                _nCommission = _slNqty * takerNcommission // 10000
                _timestamp = int(endTimestamp)
                _orderParam = _slOrderParam
                _orderID = _slOrderID
                _executed = True
                _cancelSL = False

            if _executed:
                ohRow = ohWRow[0]
                _orderParam &= ~(c.OF_NEW)
                _orderParam |= c.OF_FILLED

                oh[ohRow, c.TP_nPrice] = _nPrice
                oh[ohRow, c.TP_nQty] = _nQty
                oh[ohRow, c.TP_timestamp] = _timestamp
                oh[ohRow, c.TP_orderParam] = _orderParam
                oh[ohRow, c.TP_commission] = _nCommission
                oh[ohRow, c.TP_orderID] = _orderID
                ohWRow[0] += 1

                ohRow = ohWRow[0]
                _orderParam_ = _slOrderParam if _cancelSl else _tpOrderParam
                _orderParam_ &= ~(c.OF_NEW)
                _orderParam_ |= c.OF_CANCELED
                oh[ohRow, c.TP_nPrice] = _slNprice if _cancelSl else _tpNprice
                oh[ohRow, c.TP_nQty] = _slNqty if _cancelSl else _tpNqty
                oh[ohRow, c.TP_timestamp] = _timestamp
                oh[ohRow, c.TP_orderParam] = _orderParam_
                oh[ohRow, c.TP_commission] = None
                oh[ohRow, c.TP_orderID] = _slOrderID if _cancelSl else _tpOrderID
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
    while low <= high:
        mid: int = (low + high) // 2
        startTimestamp: int = dfm[mid, c.DFM_startTimestamp]
        endTimestamp: int = dfm[mid, c.DFM_endTimestamp]
        if startTimestamp <= timestamp <= endTimestamp:
            return dfm[mid, c.DFM_nPrice], mid
        elif timestamp < startTimestamp:
            high = mid - 1
        else:
            low = mid + 1

    if high >= 0:
        return dfm[high, c.DFM_nPrice], high
    return None
