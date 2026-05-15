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
    wRow: int = highWrow if highWrow else dfmRID[0]
    rRow: int = dfm_nRID[0]
    if rRow >= wRow:
        return

    for _row in range(rRow, wRow):
        nPrice: int = round(
            round((dfm[_row, c.DFM_nPrice] / priceMult), pricePrec) * scale
        )
        startTimestamp: int64 = dfm[_row, c.DFM_startTimestamp]
        endTimestamp: int64 = dfm[_row, c.DFM_endTimestamp]

        aoWrow: int = aoWRow[0]
        _diff_for_row: int = 0
        _nCommission: int = 0
        _timestamp: int = 0
        for aoRow in range(aoWrow):
            if not bool(np.any(active_orders[:aoWrow, 0])):
                return

            _executed = False
            aoRow = aoRow - _diff_for_row

            _nPrice: int = active_orders[aoRow, c.AO_nPrice]
            _nQty: int = active_orders[aoRow, c.AO_nQty]
            _orderParam: int = active_orders[aoRow, c.AO_orderParam]

            is_limit: bool = bool(_orderParam & c.OF_LIMIT)
            is_market_triger: bool = bool(_orderParam & c.OF_MARKET_TRIGER)
            is_buy: bool = bool(_orderParam & c.OF_BUY)

            if is_limit:
                if (is_buy and (nPrice <= _nPrice)) or (
                    not is_buy and (nPrice >= _nPrice)
                ):
                    _nPrice = _nPrice
                    _nCommission = _nQty * makerNcommission // 1000
                    _timestamp = int(startTimestamp)
                    _executed = True

            elif is_market_triger:
                if (is_buy and (nPrice >= _nPrice)) or (
                    not is_buy and (nPrice <= _nPrice)
                ):
                    slipageTicks: int = nPrice * slipage // 10000
                    _nPrice = nPrice + (slipageTicks if is_buy else -slipageTicks)
                    _nCommission = _nQty * takerNcommission // 10000
                    _timestamp = int(endTimestamp)
                    _executed = True

            if _executed:
                _orderParam &= ~(c.OF_NEW)
                _orderParam |= c.OF_FILLED

                orders_history[ohWRow[0], c.TP_nPrice] = _nPrice
                orders_history[ohWRow[0], c.TP_nQty] = _nQty
                orders_history[ohWRow[0], c.TP_timestamp] = _timestamp
                orders_history[ohWRow[0], c.TP_orderParam] = _orderParam
                orders_history[ohWRow[0], c.TP_commission] = _nCommission
                orders_history[ohWRow[0], c.TP_orderID] = active_orders[
                    aoRow, c.AO_orderID
                ]
                ohWRow[0] += 1

                if ((aoWrow - 1) - aoRow) > 0:
                    active_orders[aoRow : aoWrow - 1, :] = active_orders[
                        aoRow + 1 : aoWrow, :
                    ]
                    active_orders[aoWrow - 1, :] = None
                else:
                    active_orders[aoRow, :] = None

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
        elif timestamp < endTimestamp:
            high = mid - 1
        else:
            low = mid + 1
