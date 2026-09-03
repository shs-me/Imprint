from abc import ABC
from dataclasses import dataclass, field
from typing import override

from numba import njit
from numpy import bool_, int64
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.exchange.sim.order_stream import compact_order_book
from imprint.core.exchange.sim.tick_stream import TickStream
from imprint.core.exchange.sim.user_data_stream import UserData


@dataclass(slots=True)
class MatchingEngine(UserData, ABC):
    slippage: int = field(init=False)

    trade_readed_time: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    prepper: TickStream = field(init=False)

    @override
    def __post_init__(self) -> None:
        UserData.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.slippage = cfgAC.slippage.int_

        self.prepper = TickStream(
            symbol=self.manager.cfgCoin.symbol,
            start_date=self.manager.cfgSetup.backtest_start_date,
            end_date=self.manager.cfgSetup.backtest_end_date,
            price_mult=self.price_mult,
        )
        self.prepper.start()


@njit(cache=True)
def matching(
    trade_timestamp: int,
    trade_nPrice: int,
    order_book: NDArray[int64],
    order_id_buf: memoryview,
    obRow: memoryview,
    data_example: NDArray[int64],
    deRow: memoryview,
    slippage: int,
) -> bool:
    """Numba JIT kernel matching active limit, market, and trigger orders against incoming tick price."""

    client_in_priority: bool = False
    order_row: int = 0
    while order_row < obRow[0]:
        order_timestamp: int = order_book[order_row, c.OB_timestamp]
        order_param: int = order_book[order_row, c.OB_orderParam]
        client_order_id: int = order_book[order_row, c.OB_clientOrderID]
        order_nPrice: int = order_book[order_row, c.OB_nPrice]
        order_nQty: int = order_book[order_row, c.OB_nQty]

        data = None
        if bool(order_param & c.OF_NEW):
            if trade_timestamp >= order_timestamp:
                data_ = _processing_order(
                    trade_timestamp=trade_timestamp,
                    trade_nPrice=trade_nPrice,
                    order_nPrice=order_nPrice,
                    order_param=order_param,
                    nQty=order_nQty,
                    client_order_id=client_order_id,
                    order_book=order_book,
                    obRow=obRow,
                    order_id=order_id_buf[0],
                    slippage=slippage,
                )
                if data_ is not None:
                    data_example[deRow[0], :] = data_
                    data = data_example[deRow[0], :]
                    deRow[0] += 1
                    order_id_buf[0] += 1

        elif bool(order_param & c.OF_CANCELED):
            data_example[deRow[0], :] = (
                trade_timestamp,
                order_param,
                order_id_buf[0],
                order_nPrice,
                order_nQty,
                0,
                0,
                0,
            )

            data = data_example[deRow[0], :]
            order_id_buf[0] += 1
            deRow[0] += 1

        if data is not None:
            compact_order_book(order_row, obRow, order_book)
            client_in_priority = True
        else:
            order_row += 1

    return client_in_priority


@njit(cache=True)
def _processing_order(
    trade_timestamp: int,
    trade_nPrice: int,
    order_nPrice: int,
    order_param: int,
    nQty: int,
    client_order_id: int,
    order_book: NDArray[int64],
    obRow: memoryview,
    order_id: int,
    slippage: int,
) -> tuple[int, int, int, int, int, int, int, int] | None:
    """Numba JIT kernel evaluating individual order fill conditions, slippage, and OCO cancellations."""

    is_buy: bool = bool(order_param & c.OF_BUY)

    nPrice = trade_nPrice
    if bool(order_param & c.OF_MARKET):
        nPrice = _nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    elif bool(order_param & c.OF_LIMIT) and (
        (is_buy and (trade_nPrice <= order_nPrice))
        or (not is_buy and (trade_nPrice >= order_nPrice))
    ):
        pass

    elif bool(order_param & c.OF_MARKET_TRIGER) and (
        (is_buy and (trade_nPrice >= order_nPrice))
        or (not is_buy and (trade_nPrice <= order_nPrice))
    ):
        order_param &= ~(c.OF_MARKET_TRIGER)
        order_param |= c.OF_MARKET
        nPrice = _nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    else:
        return

    if bool(order_param & c.OF_OCO):
        mask: NDArray[bool_] = (
            order_book[: obRow[0], c.OB_clientOrderID] == client_order_id
        )
        order_book[: obRow[0], c.OB_orderParam][mask] &= ~(c.OF_NEW)
        order_book[: obRow[0], c.OB_orderParam][mask] |= c.OF_CANCELED

    order_param &= ~(c.OF_NEW | c.OF_CANCELED)
    order_param |= c.OF_FILLED

    return trade_timestamp, order_param, order_id, nPrice, nQty, 0, 0, 0


@njit(cache=True)
def _nPrice_with_slippage(nPrice: int, is_buy: bool, slippage: int) -> int:
    slipageTicks = nPrice * slippage // 10_000
    return nPrice + (slipageTicks if is_buy else -slipageTicks)
