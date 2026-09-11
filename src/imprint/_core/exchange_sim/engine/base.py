from dataclasses import dataclass, field
from typing import override

from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.account.base import to_nMargin
from imprint._core.exchange_sim.account.manager import update_equity_ohlc
from imprint._core.exchange_sim.account.position import (
    update_mae_and_mfe,
    update_position,
    update_unrealized_nPnl,
)
from imprint._core.exchange_sim.engine.matching_engine import (
    MatchingEngine,
    matching,
)
from imprint._core.exchange_sim.engine.user_data_stream import set_user_data

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


@dataclass(slots=True)
class Base(MatchingEngine):
    __mds_data_buf: memoryview = field(init=False)
    __mds_data_size: int = field(init=False)
    __mds_rid_buf: memoryview = field(init=False)
    __mds_cell_amount: int = field(init=False)

    @override
    def __post_init__(self) -> None:
        MatchingEngine.__post_init__(self)

        mds = self.manager.cfgMarketDataStream.ring_buf
        self.__mds_data_buf = mds.data_buf.cast("q")
        self.__mds_data_size = mds.data_size // 8
        self.__mds_rid_buf = mds.rid_buf
        self.__mds_cell_amount = mds.cell_amount

    def final_action(self, timestamp: int) -> None:
        self.start(timestamp)
        self.dump_equity_history()
        self.save_orders_history()

    def start(self, timestamp: int) -> None:
        _start(
            timestamp=timestamp,
            trade_read_time=self.trade_read_time,
            mds_data_buf=self.__mds_data_buf,
            mds_rid_buf=self.__mds_rid_buf,
            mds_data_size=self.__mds_data_size,
            mds_cell_amount=self.__mds_cell_amount,
            order_book=self.order_book,
            obRow=self.obRow,
            order_id_buf=self.order_id,
            uds_data_buf=self.uds_data_buf,
            uds_data_buf_size=self.uds_data_size,
            uds_data_header_buf=self.uds_data_header_buf,
            uds_wid_buf=self.uds_wid_buf,
            uds_cell_amount=self.uds_cell_amount,
            executed_orders=self.executed_orders,
            eoRow=self.eoRow,
            slippage=self.slippage,
            leverage=self.leverage,
            makerNcommission=self.makerNcommission,
            takerNcommission=self.takerNcommission,
            nBalance=self.nBalance,
            lockedNbalance=self.lockedNbalance,
            availableNbalance=self.availableNbalance,
            dynamicNbalance=self.dynamicNbalance,
            unrealizedNpnl=self.unrealizedNpnl,
            longUnrealizedNpnl=self.longUnrealizedNpnl,
            shortUnrealizedNpnl=self.shortUnrealizedNpnl,
            longNqty=self.longNqty,
            longEntryNprice=self.longEntryNprice,
            shortNqty=self.shortNqty,
            shortEntryNprice=self.shortEntryNprice,
            price_mult=self.price_mult,
            qty_mult=self.qty_mult,
            scale_mult=self.scale_mult,
            timeframe=self.timeframe,
            equity_history=self.equity_history,
            base_timestamp=self.base_timestamp,
            long_mae=self.long_mae,
            long_mfe=self.long_mfe,
            short_mae=self.short_mae,
            short_mfe=self.short_mfe,
        )


@njit(cache=True, nogil=True)
def _start(
    timestamp: int,
    trade_read_time: memoryview,
    mds_data_buf: memoryview,
    mds_data_size: int,
    mds_rid_buf: memoryview,
    mds_cell_amount: int,
    order_book: NDArray[int64],
    obRow: memoryview,
    order_id_buf: memoryview,
    uds_data_buf: memoryview,
    uds_data_buf_size: int,
    uds_data_header_buf: memoryview,
    uds_wid_buf: memoryview,
    uds_cell_amount: int,
    executed_orders: NDArray[int64],
    eoRow: memoryview,
    slippage: int,
    leverage: int,
    makerNcommission: int,
    takerNcommission: int,
    nBalance: memoryview,
    lockedNbalance: memoryview,
    availableNbalance: memoryview,
    dynamicNbalance: memoryview,
    unrealizedNpnl: memoryview,
    longUnrealizedNpnl: memoryview,
    shortUnrealizedNpnl: memoryview,
    longNqty: memoryview,
    longEntryNprice: memoryview,
    shortNqty: memoryview,
    shortEntryNprice: memoryview,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    timeframe: int,
    equity_history: NDArray[int64],
    base_timestamp: memoryview,
    long_mae: memoryview,
    long_mfe: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> None:
    while trade_read_time[0] < timestamp:
        cell: int = mds_rid_buf[1]
        start: int = cell * mds_data_size

        trade_timestamp: int = mds_data_buf[start + 2]

        if trade_timestamp > timestamp:
            trade_read_time[0] = timestamp
            return
        else:
            trade_read_time[0] = trade_timestamp

        trade_nPrice: int = mds_data_buf[start]

        new_cell: int = cell + 1
        mds_rid_buf[1] = new_cell if new_cell < mds_cell_amount else 0

        uNpnl = update_unrealized_nPnl(
            nPrice=trade_nPrice,
            unrealizedNpnl=unrealizedNpnl,
            longUnrealizedNpnl=longUnrealizedNpnl,
            shortUnrealizedNpnl=shortUnrealizedNpnl,
            longNqty=longNqty,
            longEntryNprice=longEntryNprice,
            shortNqty=shortNqty,
            shortEntryNprice=shortEntryNprice,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )
        dynamicNbalance[0] = nBalance[0] + uNpnl
        availableNbalance[0] = dynamicNbalance[0] - lockedNbalance[0]
        update_mae_and_mfe(
            longUnrealizedNpnl=longUnrealizedNpnl,
            shortUnrealizedNpnl=shortUnrealizedNpnl,
            long_mae=long_mae,
            long_mfe=long_mfe,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )
        update_equity_ohlc(
            trade_timestamp=trade_timestamp,
            current_equity=dynamicNbalance[0],
            equity_history=equity_history,
            base_timestamp=base_timestamp,
            timeframe=timeframe,
        )

        if obRow[0] == 0:
            continue

        executed: bool = matching(
            trade_timestamp=trade_timestamp,
            trade_nPrice=trade_nPrice,
            order_book=order_book,
            order_id_buf=order_id_buf,
            obRow=obRow,
            executed_orders=executed_orders,
            eoRow=eoRow,
            slippage=slippage,
        )
        if executed:
            _processing_executed_orders(
                uds_data_buf=uds_data_buf,
                uds_data_buf_size=uds_data_buf_size,
                uds_data_header_buf=uds_data_header_buf,
                uds_wid_buf=uds_wid_buf,
                uds_cell_amount=uds_cell_amount,
                executed_orders=executed_orders,
                eoRow=eoRow,
                makerNcommission=makerNcommission,
                takerNcommission=takerNcommission,
                price_mult=price_mult,
                qty_mult=qty_mult,
                scale_mult=scale_mult,
                leverage=leverage,
                nBalance=nBalance,
                lockedNbalance=lockedNbalance,
                longNqty=longNqty,
                longEntryNprice=longEntryNprice,
                shortNqty=shortNqty,
                shortEntryNprice=shortEntryNprice,
                long_mae=long_mae,
                long_mfe=long_mfe,
                short_mae=short_mae,
                short_mfe=short_mfe,
            )

        uNpnl = update_unrealized_nPnl(
            nPrice=trade_nPrice,
            unrealizedNpnl=unrealizedNpnl,
            longUnrealizedNpnl=longUnrealizedNpnl,
            shortUnrealizedNpnl=shortUnrealizedNpnl,
            longNqty=longNqty,
            longEntryNprice=longEntryNprice,
            shortNqty=shortNqty,
            shortEntryNprice=shortEntryNprice,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )
        dynamicNbalance[0] = nBalance[0] + uNpnl
        availableNbalance[0] = dynamicNbalance[0] - lockedNbalance[0]
        update_mae_and_mfe(
            longUnrealizedNpnl=longUnrealizedNpnl,
            shortUnrealizedNpnl=shortUnrealizedNpnl,
            long_mae=long_mae,
            long_mfe=long_mfe,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )
        update_equity_ohlc(
            trade_timestamp=trade_timestamp,
            current_equity=dynamicNbalance[0],
            equity_history=equity_history,
            base_timestamp=base_timestamp,
            timeframe=timeframe,
        )

        if executed:
            break


@njit(cache=True)
def _processing_executed_orders(
    uds_data_buf: memoryview,
    uds_data_buf_size: int,
    uds_data_header_buf: memoryview,
    uds_wid_buf: memoryview,
    uds_cell_amount: int,
    executed_orders: NDArray[int64],
    eoRow: memoryview,
    makerNcommission: int,
    takerNcommission: int,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    leverage: int,
    nBalance: memoryview,
    lockedNbalance: memoryview,
    longNqty: memoryview,
    longEntryNprice: memoryview,
    shortNqty: memoryview,
    shortEntryNprice: memoryview,
    long_mae: memoryview,
    long_mfe: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> None:
    for eo_row in range(eoRow[0]):
        eoRow[0] -= 1

        order_param = executed_orders[eo_row, c.TP_order_param]
        nPrice = executed_orders[eo_row, c.TP_nPrice]
        nQty = executed_orders[eo_row, c.TP_nQty]

        is_buy: bool = bool(order_param & c.OF_BUY)
        is_long: bool = bool(order_param & c.OF_LONG)
        is_maker: bool = bool(order_param & c.OF_LIMIT)

        is_open: bool = (is_buy and is_long) or (not is_buy and not is_long)

        if bool(order_param & c.OF_FILLED):
            rate: int = makerNcommission if is_maker else takerNcommission
            commission: float = (
                ((nPrice / price_mult) * (nQty / qty_mult)) * rate / 10_000
            )
            nCommission: int = round(commission * scale_mult)
            executed_orders[eo_row, c.TP_nCommission] = nCommission

            if not is_open:
                if is_long:
                    executed_orders[eo_row, c.TP_nMAE] = long_mae[0]
                    executed_orders[eo_row, c.TP_nMFE] = long_mfe[0]
                else:
                    executed_orders[eo_row, c.TP_nMAE] = long_mae[0]
                    executed_orders[eo_row, c.TP_nMFE] = long_mfe[0]

            update_position(
                nPrice=nPrice,
                nQty=nQty,
                is_long=is_long,
                is_open=is_open,
                is_maker=is_maker,
                nCommission=nCommission,
                price_mult=price_mult,
                qty_mult=qty_mult,
                scale_mult=scale_mult,
                leverage=leverage,
                nBalance=nBalance,
                lockedNbalance=lockedNbalance,
                longNqty=longNqty,
                longEntryNprice=longEntryNprice,
                shortNqty=shortNqty,
                shortEntryNprice=shortEntryNprice,
                long_mae=long_mae,
                long_mfe=long_mfe,
                short_mae=short_mae,
                short_mfe=short_mfe,
            )

        elif bool(order_param & c.OF_NEW) and (not is_maker):
            continue

        elif bool(order_param & c.OF_CANCELED) and is_open:
            lockedNbalance[0] -= to_nMargin(
                nPrice, nQty, leverage, price_mult, qty_mult, scale_mult
            )

        set_user_data(
            data=executed_orders[eo_row, :],
            uds_data_buf=uds_data_buf,
            uds_data_buf_size=uds_data_buf_size,
            uds_data_header_buf=uds_data_header_buf,
            uds_wid_buf=uds_wid_buf,
            uds_cell_amount=uds_cell_amount,
        )
