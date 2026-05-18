import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from core import constant as c
from core.engine.agents_utils.execution.trade_manager import (
    OPEN_ORDER,
    SL_ORDER,
    TP_ORDER,
    TradeManager,
)
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
        self.dfmRid: memoryview = memoryview(bytearray(8)).cast("q")

    @property
    def dfm(self) -> NDArray[int64]:
        return self.dfm_2 if (self.space_flag[0] == 0) else self.dfm_1

    @property
    def dfmWid(self) -> memoryview:
        return self.dfm_2RID if (self.space_flag[0] == 0) else self.dfm_1RID

    def prepare_dfm(self, timestamp: int | None) -> None:
        aoWRow, dfmWid, dfmRid = self.tm.aoWRow, self.dfmWid, self.dfmRid
        _, dfm = self.con, self.dfm
        # - - -
        if timestamp is not None:
            if timestamp <= dfm[dfmWid[0], c.DFM_endTimestamp]:
                wRow = find_row(timestamp, dfm, dfmWid[0])
            else:
                wRow = dfmWid[0]
        else:
            wRow = dfmWid[0]

        rRow = dfmRid[0] = wRow if (aoWRow[0] == 0) else dfmRid[0]
        if rRow < wRow:
            for row in range(rRow, wRow):
                nPrice: int = _.to_nPrice(_.to_fpPrice(dfm[row, c.DFM_endTimestamp]))
                endTimestamp: int = int(dfm[row, c.DFM_endTimestamp])

                if aoWRow[0] == 0:
                    return

                aoWrow: int = aoWRow[0]
                for aoRow in range(aoWrow):
                    if self.check_open_order(aoRow, nPrice, endTimestamp) is False:
                        if self.check_tp_order(aoRow, nPrice, endTimestamp):
                            if self.check_sl_order(aoRow, nPrice, endTimestamp):
                                continue

                        aoWRow[0] -= 1

                dfmRid[0] += 1

    def check_open_order(self, aoRow: int, _nPrice: int, endTimestamp: int) -> bool:
        ao, _ = self.tm.active_orders, self.con
        # - - -
        if ao[OPEN_ORDER, aoRow, c.AO_nPrice] is None:
            return False

        timestamp: int = ao[OPEN_ORDER, aoRow, c.AO_timestamp]
        if timestamp > endTimestamp:
            return True

        nPrice: int = ao[OPEN_ORDER, aoRow, c.AO_nPrice]
        nQty: int = ao[OPEN_ORDER, aoRow, c.AO_nQty]
        orderParam: int = ao[OPEN_ORDER, aoRow, c.AO_orderParam]

        is_market: bool = bool(orderParam & c.OF_MARKET)
        is_buy: bool = bool(orderParam & c.OF_BUY)

        is_maker = False
        if is_market:
            slipageTicks = nPrice * self.con.slipage // 10000
            nPrice = nPrice + (slipageTicks if is_buy else -slipageTicks)
        else:
            if (is_buy and (_nPrice <= nPrice)) or (not is_buy and (_nPrice >= nPrice)):
                is_maker = True
            else:
                return True

        nCommission: int = (
            nQty * (_.makerNcommission if is_maker else _.takerNcommission) // 1000
        )
        orderParam &= ~(c.OF_NEW)
        orderParam |= c.OF_FILLED
        self.tm.update_orders_history(
            nPrice, nQty, int(endTimestamp), orderParam, None, nCommission
        )
        ao[OPEN_ORDER, aoRow, :] = None

        nPriceTP = _.TPdevNprice(nPrice, is_buy)
        tpOrderParam = 0
        tpOrderParam |= c.OF_LONG if is_buy else c.OF_SHORT
        tpOrderParam |= c.OF_SELL if is_buy else c.OF_BUY
        tpOrderParam |= c.OF_LIMIT | c.OF_NEW
        timestamp = int(endTimestamp + _.latencyMs)
        self.tm.set_active_order(
            nPriceTP, nQty, timestamp, tpOrderParam, None, aoRow, is_tp=True
        )
        nPriceSL = _.SLdevNprice(nPrice, is_buy)
        slOrderParam = 0
        slOrderParam |= c.OF_LONG if is_buy else c.OF_SHORT
        slOrderParam |= c.OF_SELL if is_buy else c.OF_BUY
        slOrderParam |= c.OF_MARKET_TRIGER | c.OF_NEW
        self.tm.set_active_order(
            nPriceSL, nQty, timestamp, slOrderParam, None, aoRow, is_tp=False
        )

        self.tm.prepare_trades()
        return True

    def check_tp_order(self, aoRow: int, _nPrice: int, endTimestamp: int) -> bool:
        ao, _ = self.tm.active_orders, self.con
        # - - -
        timestamp: int = ao[TP_ORDER, aoRow, c.AO_timestamp]
        if timestamp > endTimestamp:
            return True

        nPrice: int = ao[TP_ORDER, aoRow, c.AO_nPrice]
        nQty: int = ao[TP_ORDER, aoRow, c.AO_nQty]
        orderParam: int = ao[TP_ORDER, aoRow, c.AO_orderParam]

        is_buy: bool = bool(orderParam & c.OF_BUY)

        if (is_buy and (_nPrice <= nPrice)) or (not is_buy and (_nPrice >= nPrice)):
            nCommission: int = nQty * _.makerNcommission // 1000
            orderParam &= ~(c.OF_NEW)
            orderParam |= c.OF_FILLED
            self.tm.update_orders_history(
                nPrice, nQty, int(endTimestamp), orderParam, None, nCommission
            )
            ao[TP_ORDER, aoRow, :] = None
            self.cancel_active_order(aoRow, int(endTimestamp), SL_ORDER)
            return False
        return True

    def check_sl_order(self, aoRow: int, _nPrice: int, endTimestamp: int) -> bool:
        ao, _ = self.tm.active_orders, self.con
        # - - -
        timestamp: int = ao[SL_ORDER, aoRow, c.AO_timestamp]
        if timestamp > endTimestamp:
            return True

        nPrice: int = ao[SL_ORDER, aoRow, c.AO_nPrice]
        nQty: int = ao[SL_ORDER, aoRow, c.AO_nQty]
        orderParam: int = ao[SL_ORDER, aoRow, c.AO_orderParam]

        is_buy: bool = bool(orderParam & c.OF_BUY)

        if (is_buy and (_nPrice >= nPrice)) or (not is_buy and (_nPrice <= nPrice)):
            nCommission: int = nQty * _.takerNcommission // 1000
            orderParam &= ~(c.OF_NEW)
            orderParam |= c.OF_FILLED
            self.tm.update_orders_history(
                nPrice, nQty, int(endTimestamp), orderParam, None, nCommission
            )
            ao[SL_ORDER, aoRow, :] = None
            self.cancel_active_order(aoRow, int(endTimestamp), TP_ORDER)
            return False
        return True

    def cancel_active_order(self, aoRow: int, timestamp: int, typeOrder: int) -> None:
        nPrice: int = self.tm.active_orders[typeOrder, aoRow, c.AO_nPrice]
        nQty: int = self.tm.active_orders[typeOrder, aoRow, c.AO_nQty]
        orderParam: int = self.tm.active_orders[typeOrder, aoRow, c.AO_orderParam]

        orderParam &= ~(c.OF_NEW)
        orderParam |= c.OF_CANCELED

        self.tm.update_orders_history(nPrice, nQty, timestamp, orderParam, None)
        self.tm.prepare_trades()
        self.tm.active_orders[typeOrder, aoRow, :] = None


@njit(cache=True)
def find_row(timestamp: int, dfm: NDArray[int64], dfmWrow: int) -> int:
    return np.where(dfm[:dfmWrow, c.DFM_endTimestamp] >= timestamp)[0][0]
