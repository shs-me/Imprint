from abc import ABC
from dataclasses import dataclass, field
from typing import override

from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.engine.order_stream import compact_order_book
from imprint._core.exchange_sim.engine.user_data_stream import UserData


@dataclass(slots=True)
class MatchingEngine(UserData, ABC):
    slippage: int = field(init=False)

    trade_read_time: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @override
    def __post_init__(self) -> None:
        UserData.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.slippage = cfgAC.slippage.fixed


@njit(cache=True)
def matching(
    trade_timestamp: int,
    trade_nPrice: int,
    order_book: NDArray[int64],
    order_id_buf: memoryview,
    obRow: memoryview,
    executed_orders: NDArray[int64],
    eoRow: memoryview,
    slippage: int,
) -> bool:
    client_in_priority: bool = False
    for row in range(obRow[0]):
        order_timestamp: int = order_book[row, c.OB_timestamp]
        order_param: int = order_book[row, c.OB_orderParam]
        client_order_id: int = order_book[row, c.OB_clientOrderID]

        executed: bool = False
        if (trade_timestamp >= order_timestamp) and (
            (
                bool(order_param & c.OF_NEW)
                and _processing_new_order(
                    trade_timestamp=trade_timestamp,
                    trade_nPrice=trade_nPrice,
                    order_nPrice=order_book[row, c.OB_nPrice],
                    order_param=order_param,
                    nQty=order_book[row, c.OB_nQty],
                    order_id=order_id_buf[0],
                    client_order_id=client_order_id,
                    slippage=slippage,
                    executed_orders=executed_orders,
                    eoRow=eoRow,
                )
            )
            or (
                bool(order_param & c.OF_CANCEL)
                and _processing_cancel_order(
                    trade_timestamp=trade_timestamp,
                    order_book=order_book,
                    obRow=obRow,
                    order_id=order_id_buf[0],
                    client_order_id=client_order_id,
                    executed_orders=executed_orders,
                    eoRow=eoRow,
                )
            )
        ):
            order_book[row, c.OB_orderParam] &= ~(c.OF_CANCEL | c.OF_NEW)
            order_book[row, c.OB_orderParam] |= c.OF_CANCELED | c.OF_FILLED
            order_id_buf[0] += 1
            executed = True

        if executed:
            client_in_priority = True

    compact_order_book(obRow, order_book)
    return client_in_priority


@njit(cache=True)
def _processing_new_order(
    trade_timestamp: int,
    trade_nPrice: int,
    order_nPrice: int,
    order_param: int,
    nQty: int,
    order_id: int,
    client_order_id: int,
    slippage: int,
    executed_orders: NDArray[int64],
    eoRow: memoryview,
) -> bool:
    is_buy: bool = bool(order_param & c.OF_BUY)

    if bool(order_param & c.OF_MARKET):
        nPrice = _nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    elif bool(order_param & c.OF_LIMIT) and (
        (is_buy and (trade_nPrice <= order_nPrice))
        or (not is_buy and (trade_nPrice >= order_nPrice))
    ):
        nPrice = order_nPrice

    elif bool(order_param & c.OF_MARKET_TRIGGER) and (
        (is_buy and (trade_nPrice >= order_nPrice))
        or (not is_buy and (trade_nPrice <= order_nPrice))
    ):
        order_param &= ~(c.OF_MARKET_TRIGGER)
        order_param |= c.OF_MARKET
        nPrice = _nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    else:
        return False

    order_param &= ~(c.OF_NEW)
    order_param |= c.OF_FILLED

    executed_orders[eoRow[0], c.TP_timestamp] = trade_timestamp
    executed_orders[eoRow[0], c.TP_order_param] = order_param
    executed_orders[eoRow[0], c.TP_order_id] = order_id
    executed_orders[eoRow[0], c.TP_client_order_id] = client_order_id
    executed_orders[eoRow[0], c.TP_nPrice] = nPrice
    executed_orders[eoRow[0], c.TP_nQty] = nQty
    executed_orders[eoRow[0], c.TP_nCommission] = 0
    executed_orders[eoRow[0], c.TP_nMAE] = 0
    executed_orders[eoRow[0], c.TP_nMFE] = 0
    eoRow[0] += 1
    return True


@njit(cache=True)
def _nPrice_with_slippage(nPrice: int, is_buy: bool, slippage: int) -> int:
    slipageTicks = nPrice * slippage // 10_000
    return nPrice + (slipageTicks if is_buy else -slipageTicks)


@njit(cache=True)
def _processing_cancel_order(
    trade_timestamp: int,
    order_book: NDArray[int64],
    obRow: memoryview,
    order_id: int,
    client_order_id: int,
    executed_orders: NDArray[int64],
    eoRow: memoryview,
) -> bool:
    for row in range(obRow[0]):
        if order_book[row, c.OB_clientOrderID] == client_order_id:
            order_param: int = order_book[row, c.OB_orderParam]
            nPrice: int = order_book[row, c.OB_nPrice]
            nQty: int = order_book[row, c.OB_nQty]

            order_param &= ~(c.OF_NEW)
            order_param |= c.OF_CANCELED

            order_book[row, c.OB_orderParam] = order_param

            executed_orders[eoRow[0], c.TP_timestamp] = trade_timestamp
            executed_orders[eoRow[0], c.TP_order_param] = order_param
            executed_orders[eoRow[0], c.TP_order_id] = order_id
            executed_orders[eoRow[0], c.TP_client_order_id] = client_order_id
            executed_orders[eoRow[0], c.TP_nPrice] = nPrice
            executed_orders[eoRow[0], c.TP_nQty] = nQty
            executed_orders[eoRow[0], c.TP_nCommission] = 0
            executed_orders[eoRow[0], c.TP_nMAE] = 0
            executed_orders[eoRow[0], c.TP_nMFE] = 0
            eoRow[0] += 1
            return True

    return False
