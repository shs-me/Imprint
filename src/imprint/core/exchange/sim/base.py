import time
from dataclasses import dataclass

from numba import njit
from numpy import int64, uint8
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.exchange.account.manager import update_equity_ohlc
from imprint.core.exchange.account.position import (
    update_mae_and_mfe,
    update_position,
    update_unrealized_nPnl,
)
from imprint.core.exchange.sim.matching_engine import MatchingEngine, matching
from imprint.core.exchange.sim.user_data_stream import set_user_data

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


@dataclass(slots=True)
class Base(MatchingEngine):
    def start(self, timestamp: int) -> None:
        while True:
            if _start(
                timestamp=timestamp,
                trade_read_time=self.trade_read_time,
                dfm=self.prepare.dfm,
                dfmRid=self.prepare.dfmRid,
                dfmWid=self.prepare.dfmWid,
                order_book=self.order_book,
                obRow=self.obRow,
                order_id_buf=self.order_id,
                gus_data_buf=self.gus_data_buf,
                gus_data_buf_size=self.gus_data_size,
                gus_data_header=self.gus_data_header,
                gus_wid=self.gus_wid,
                gus_cell_amount=self.gus_cell_amount,
                data_example=self.data_example,
                deRow=self.deRow,
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
            ):
                break
            else:
                if self.prepare.error is not None:
                    raise RuntimeError(self.prepare.error)
                else:
                    while self.prepare.dfmWid[0] == self.prepare.dfmRid[0]:
                        if self.prepare.complete:
                            return

                        time.sleep(0)


@njit(cache=True, nogil=True)
def _start(
    timestamp: int,
    trade_read_time: memoryview,
    dfm: NDArray[int64],
    dfmRid: memoryview,
    dfmWid: memoryview,
    order_book: NDArray[int64],
    obRow: memoryview,
    order_id_buf: memoryview,
    gus_data_buf: NDArray[uint8],
    gus_data_buf_size: int,
    gus_data_header: memoryview,
    gus_wid: memoryview,
    gus_cell_amount: int,
    data_example: NDArray[int64],
    deRow: memoryview,
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
) -> bool:
    max_row: int = dfm.shape[0]
    while trade_read_time[0] < timestamp:
        row: int = dfmRid[0]

        if row == dfmWid[0]:
            return False

        trade_timestamp: int = dfm[row, 1]

        if trade_timestamp > timestamp:
            trade_read_time[0] = timestamp
            return True
        else:
            trade_read_time[0] = trade_timestamp

        new_row: int = row + 1
        dfmRid[0] = new_row if (new_row < max_row) else 0

        trade_nPrice: int = dfm[row, 0]

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
            data_example=data_example,
            deRow=deRow,
            slippage=slippage,
        )
        if executed:
            _processing_executed_orders(
                gus_data_buf=gus_data_buf,
                gus_data_buf_size=gus_data_buf_size,
                gus_data_header=gus_data_header,
                gus_wid=gus_wid,
                gus_cell_amount=gus_cell_amount,
                data_example=data_example,
                deRow=deRow,
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

    return True


@njit(cache=True)
def _processing_executed_orders(
    gus_data_buf: NDArray[uint8],
    gus_data_buf_size: int,
    gus_data_header: memoryview,
    gus_wid: memoryview,
    gus_cell_amount: int,
    data_example: NDArray[int64],
    deRow: memoryview,
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
    max_de_row: int = deRow[0]
    for de_row in range(max_de_row):
        deRow[0] -= 1
        (
            _trade_timestamp,
            order_param,
            _order_id,
            nPrice,
            nQty,
            nCommission,
            _mae,
            _mfe,
        ) = data_example[de_row, :]

        is_buy = bool(order_param & c.OF_BUY)
        is_long = bool(order_param & c.OF_LONG)
        is_maker = bool(order_param & c.OF_LIMIT)

        is_open = (is_buy and is_long) or (not is_buy and not is_long)

        if bool(order_param & c.OF_FILLED):
            rate: int = makerNcommission if is_maker else takerNcommission
            commission: float = (
                ((nPrice / price_mult) * (nQty / qty_mult)) * rate / 10_000
            )
            nCommission = round(commission * scale_mult)
            data_example[de_row, 5] = nCommission

            if not is_open:
                if is_long:
                    data_example[de_row, 6] = long_mae[0]
                    data_example[de_row, 7] = long_mfe[0]
                else:
                    data_example[de_row, 6] = short_mae[0]
                    data_example[de_row, 7] = short_mfe[0]
            else:
                data_example[de_row, 6] = 0
                data_example[de_row, 7] = 0

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

        set_user_data(
            data=data_example[de_row, :].view(uint8),
            gus_data_buf=gus_data_buf,
            gus_data_buf_size=gus_data_buf_size,
            gus_data_header=gus_data_header,
            gus_wid=gus_wid,
            gus_cell_amount=gus_cell_amount,
        )
