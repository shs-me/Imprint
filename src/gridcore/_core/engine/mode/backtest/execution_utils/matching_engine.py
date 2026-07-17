from numba import njit
from numpy import int64
from numpy.typing import NDArray

from ..... import constant as c
from ....base.utils.tm_con import TradeConverter
from .data_prepper import DataPrepper
from .trade_manager import (
    OPEN_ORDER,
    SL_ORDER,
    TP_ORDER,
    TradeManager,
)


class MatchingEngine:
    def __init__(
        self, con: TradeConverter, tm: TradeManager, prepper: DataPrepper
    ) -> None:
        self.con: TradeConverter = con
        self.tm: TradeManager = tm
        self.prepper: DataPrepper = prepper

    def check_open_order(self, aoRow: int, _nPrice: int, endTimestamp: int) -> bool:
        tm, _ = self.tm, self.con
        # - - -
        if tm.active_orders[OPEN_ORDER, aoRow, c.AO_nPrice] is None:
            return False

        timestamp: int = tm.active_orders[OPEN_ORDER, aoRow, c.AO_timestamp]
        if timestamp > endTimestamp:
            return True

        nPrice: int = tm.active_orders[OPEN_ORDER, aoRow, c.AO_nPrice]
        nQty: int = tm.active_orders[OPEN_ORDER, aoRow, c.AO_nQty]
        orderParam: int = tm.active_orders[OPEN_ORDER, aoRow, c.AO_orderParam]

        is_market: bool = bool(orderParam & c.OF_MARKET)
        is_long: bool = bool(orderParam & c.OF_LONG)
        is_buy: bool = bool(orderParam & c.OF_BUY)

        if is_market:
            nPrice = _.nPriceWithSlippage(_nPrice, is_buy)
            _.lockedNbalance = _.to_nMargin(nPrice, nQty)
            is_maker = False
        else:
            if (is_buy and (_nPrice <= nPrice)) or (not is_buy and (_nPrice >= nPrice)):
                is_maker = True
            else:
                return True

        orderParam &= ~(c.OF_NEW)
        orderParam |= c.OF_FILLED
        nCommission = _.to_nCommission(nQty, is_maker)
        tm.updatePosition(nPrice, nQty, nCommission, True, is_long)
        tm.update_orders_history(
            nPrice, nQty, int(endTimestamp), orderParam, None, nCommission
        )
        tm.active_orders[OPEN_ORDER, aoRow, :] = None

        nPriceTP = _.TPdevNprice(nPrice, is_long)
        tpOrderParam = 0
        tpOrderParam |= c.OF_LONG if is_long else c.OF_SHORT
        tpOrderParam |= c.OF_SELL if is_buy else c.OF_BUY
        tpOrderParam |= c.OF_LIMIT | c.OF_NEW
        timestamp = int(endTimestamp + _.latencyMs)
        tm.set_active_order(
            nPriceTP, nQty, timestamp, tpOrderParam, None, aoRow, is_tp=True
        )

        nPriceSL = _.SLdevNprice(nPrice, is_long)
        slOrderParam = 0
        slOrderParam |= c.OF_LONG if is_long else c.OF_SHORT
        slOrderParam |= c.OF_SELL if is_buy else c.OF_BUY
        slOrderParam |= c.OF_MARKET_TRIGER | c.OF_NEW
        tm.set_active_order(
            nPriceSL, nQty, timestamp, slOrderParam, None, aoRow, is_tp=False
        )
        return False

    def check_tp_order(self, aoRow: int, _nPrice: int, endTimestamp: int) -> bool:
        tm, _ = self.tm, self.con
        # - - -
        timestamp: int = tm.active_orders[TP_ORDER, aoRow, c.AO_timestamp]
        if timestamp > endTimestamp:
            return True

        nPrice: int = tm.active_orders[TP_ORDER, aoRow, c.AO_nPrice]
        nQty: int = tm.active_orders[TP_ORDER, aoRow, c.AO_nQty]
        orderParam: int = tm.active_orders[TP_ORDER, aoRow, c.AO_orderParam]

        is_long: bool = bool(orderParam & c.OF_LONG)
        is_buy: bool = bool(orderParam & c.OF_BUY)

        if (is_buy and (_nPrice <= nPrice)) or (not is_buy and (_nPrice >= nPrice)):
            orderParam &= ~(c.OF_NEW)
            orderParam |= c.OF_FILLED
            nCommission = _.to_nCommission(nQty, True)
            tm.updatePosition(nPrice, nQty, nCommission, False, is_long)
            tm.update_orders_history(
                nPrice, nQty, int(endTimestamp), orderParam, None, nCommission
            )
            tm.active_orders[TP_ORDER, aoRow, :] = None
            tm.cancel_active_order(aoRow, int(endTimestamp), SL_ORDER)
            return False
        return True

    def check_sl_order(self, aoRow: int, _nPrice: int, endTimestamp: int) -> bool:
        tm, _ = self.tm, self.con
        # - - -
        timestamp: int = tm.active_orders[SL_ORDER, aoRow, c.AO_timestamp]
        if timestamp > endTimestamp:
            return True

        nPrice: int = tm.active_orders[SL_ORDER, aoRow, c.AO_nPrice]
        nQty: int = tm.active_orders[SL_ORDER, aoRow, c.AO_nQty]
        orderParam: int = tm.active_orders[SL_ORDER, aoRow, c.AO_orderParam]

        is_long: bool = bool(orderParam & c.OF_LONG)
        is_buy: bool = bool(orderParam & c.OF_BUY)

        if (is_buy and (_nPrice >= nPrice)) or (not is_buy and (_nPrice <= nPrice)):
            orderParam &= ~(c.OF_NEW)
            orderParam |= c.OF_FILLED
            nPrice = _.nPriceWithSlippage(_nPrice, is_buy)
            nCommission: int = _.to_nCommission(nQty, False)
            tm.updatePosition(nPrice, nQty, nCommission, False, is_long)
            tm.update_orders_history(
                nPrice, nQty, int(endTimestamp), orderParam, None, nCommission
            )
            tm.active_orders[SL_ORDER, aoRow, :] = None
            tm.cancel_active_order(aoRow, int(endTimestamp), TP_ORDER)
            return False
        return True


@njit(cached=True)
def matching(
    timestamp: int,
    orderBook: NDArray[int64],
    dfm: NDArray[int64],
    dfmRid: memoryview,
    dfmWid: memoryview,
) -> None:
    _timestamp = 0
    while _timestamp != timestamp:
        while dfmRid[0] != dfmWid[0]:
            nPrice, _timestamp = dfm[dfmRid[0], :]


def processing_market_orders() -> None:
    pass


def processing_limit_orders() -> None:
    pass


def processing_cond_orders() -> None:
    pass
