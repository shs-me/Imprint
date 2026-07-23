import time

from numba import njit
from numpy import int64, uint8
from numpy.typing import NDArray

from ..... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from . import matching_engine as me


class AccountManager(me.MatchingEngine):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)

        cfgCoin = manager.cfgCoin
        self.price_prec: int = cfgCoin.price_prec
        self.qty_prec: int = cfgCoin.qty_prec
        self.price_mult: int = cfgCoin.price_mult
        self.qty_mult: int = cfgCoin.qty_mult

        cfgAC = manager.cfgAccount
        self.scale_prec: int = cfgAC.scale_prec
        self.scale_mult: int = cfgAC.scale_mult
        self.latency: int = cfgAC.latency_ms
        self.leverage: int = cfgAC.leverage
        self.takerNcommission: int = cfgAC.taker_commission
        self.makerNcommission: int = cfgAC.maker_commission
        self.startNbalance: int = round(cfgAC.balance * self.scale_mult)

        self.nBalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.lockedNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.availableNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.longNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self.longEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")

        self.unrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.longUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")

        self.nBalance[0] = self.startNbalance
        self.availableNbalance[0] = self.startNbalance

        self.args = (
            self.trade_readed_time,
            self.prepper.dfm,
            self.prepper.dfmRid,
            self.prepper.dfmWid,
            self.order_book,
            self.obRow,
            self.order_id,
            self.data_buf,
            self.data_buf_size,
            self.data_header,
            self.data_example,
            self.deRow,
            self.slippage,
            self.latency,
            self.leverage,
            self.makerNcommission,
            self.takerNcommission,
            self.nBalance,
            self.lockedNbalance,
            self.availableNbalance,
            self.unrealizedNpnl,
            self.longUnrealizedNpnl,
            self.shortUnrealizedNpnl,
            self.longNqty,
            self.longEntryNprice,
            self.shortNqty,
            self.shortEntryNprice,
            self.price_mult,
            self.qty_mult,
            self.scale_mult,
            self.writer_id,
            self.cell_amount,
        )

    def send_order(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        is_long = bool(order_param & c.OF_LONG)
        is_buy = bool(order_param & c.OF_BUY)
        if (is_buy and is_long) or (not is_long and not is_buy):
            self.lockedNbalance[0] += _to_nMargin(
                nPrice,
                nQty,
                self.leverage,
                self.price_mult,
                self.qty_mult,
                self.scale_mult,
            )

        self._update_order_book(
            timestamp=timestamp + self.latency,
            order_param=order_param,
            client_order_id=client_order_id,
            nPrice=nPrice,
            nQty=nQty,
        )

    def start(self, timestamp: int) -> None:
        while True:
            if _start(timestamp=timestamp, args=self.args):
                break
            else:
                if self.prepper.error is not None:
                    raise RuntimeError(self.prepper.error)
                else:
                    while self.prepper.dfmWid[0] == self.prepper.dfmRid[0]:
                        if self.prepper.complete:
                            return

                        time.sleep(0)


@njit(cache=True, nogil=True)
def _start(
    timestamp: int,
    args: tuple[
        memoryview,
        NDArray[int64],
        memoryview,
        memoryview,
        NDArray[int64],
        memoryview,
        memoryview,
        NDArray[uint8],
        int,
        memoryview,
        NDArray[int64],
        memoryview,
        int,
        int,
        int,
        int,
        int,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        int,
        int,
        int,
        memoryview,
        int,
    ],
) -> bool:
    time_readed_trade, dfm, dfmRid, dfmWid = args[0:4]
    order_book, obRow, order_id_buf = args[4:7]
    data_buf, data_buf_size, data_header, data_example, deRow = args[7:12]
    slippage, latency, leverage, makerNcommission, takerNcommission = args[12:17]
    nBalance, lockedNbalance, availableNbalance = args[17:20]
    unrealizedNpnl, longUnrealizedNpnl, shortUnrealizedNpnl = args[20:23]
    longNqty, longEntryNprice, shortNqty, shortEntryNprice = args[23:27]
    price_mult, qty_mult, scale_mult = args[27:30]
    writer_id, cell_amount = args[30:32]

    max_row: int = dfm.shape[0]
    while time_readed_trade[0] < timestamp:
        row: int = dfmRid[0]

        if row == dfmWid[0]:
            return False

        new_row: int = row + 1
        dfmRid[0] = new_row if (new_row < max_row) else 0

        trade_nPrice: int = dfm[row, 0]
        time_readed_trade[0] = dfm[row, 1]

        if longNqty[0] or shortNqty[0]:
            uNpnl = _to_unrealized_nPnl(
                trade_nPrice=trade_nPrice,
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
            availableNbalance[0] = nBalance[0] - uNpnl - lockedNbalance[0]

        if obRow[0] == 0:
            continue

        trade_timestamp: int = dfm[row, 1]

        executed: bool = me._matching(
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
            _update_positions(
                obRow=obRow,
                data_buf=data_buf,
                data_buf_size=data_buf_size,
                data_header=data_header,
                writer_id=writer_id,
                cell_amount=cell_amount,
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
            )

        if longNqty[0] or shortNqty[0]:
            uNpnl = _to_unrealized_nPnl(
                trade_nPrice=trade_nPrice,
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
            availableNbalance[0] = nBalance[0] - uNpnl - lockedNbalance[0]

        if executed:
            break

    return True


@njit(cache=True)
def _update_positions(
    obRow: memoryview,
    data_buf: NDArray[uint8],
    data_buf_size: int,
    data_header: memoryview,
    writer_id: memoryview,
    cell_amount: int,
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
) -> None:
    max_de_row: int = deRow[0]
    for de_row in range(max_de_row):
        deRow[0] -= 1
        trade_timestamp, order_param, order_id, nPrice, nQty, nCommission = (
            data_example[de_row, :]
        )

        is_buy = bool(order_param & c.OF_BUY)
        is_long = bool(order_param & c.OF_LONG)
        is_limit = bool(order_param & c.OF_LIMIT)

        is_open = (is_buy and is_long) or (not is_buy and not is_long)

        if bool(order_param & c.OF_FILLED):
            rate: int = makerNcommission if is_limit else takerNcommission
            commission: float = (
                ((nPrice / price_mult) * (nQty / qty_mult)) * rate / 10_000
            )
            data_example[de_row, 5] = round(commission * scale_mult)

            _update_position(
                nPrice=nPrice,
                nQty=nQty,
                is_long=is_long,
                is_open=is_open,
                nCommission=nCommission,
                obRow=obRow,
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
            )

        me._set_user_data(
            data=data_example[de_row, :].view(uint8),
            data_buf=data_buf,
            data_buf_size=data_buf_size,
            data_header=data_header,
            writer_id=writer_id,
            cell_amount=cell_amount,
        )


@njit(cache=True)
def _update_position(
    nPrice: int,
    nQty: int,
    is_long: bool,
    is_open: bool,
    nCommission: int,
    obRow: memoryview,
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
) -> None:
    nBalance[0] -= nCommission
    if is_long:
        if is_open:
            if longNqty[0]:
                longEntryNprice[0] = (
                    (longEntryNprice[0] * longNqty[0]) + (nPrice * nQty)
                ) // (longNqty[0] + nQty)
            else:
                longEntryNprice[0] = nPrice

            longNqty[0] += nQty
        else:
            lockedNbalance[0] -= _to_nMargin(
                longEntryNprice[0], nQty, leverage, price_mult, qty_mult, scale_mult
            )
            nBalance[0] += _to_nPnl(
                nPrice,
                nQty,
                is_long,
                longEntryNprice[0],
                shortEntryNprice[0],
                price_mult,
                qty_mult,
                scale_mult,
            )
            longNqty[0] -= nQty

        if not longNqty[0]:
            longEntryNprice[0] = 0

    else:
        if is_open:
            if shortNqty[0]:
                shortEntryNprice[0] = (
                    (shortEntryNprice[0] * shortNqty[0]) + (nPrice * nQty)
                ) // (shortNqty[0] + nQty)
            else:
                shortEntryNprice[0] = nPrice

            shortNqty[0] += nQty
        else:
            lockedNbalance[0] -= _to_nMargin(
                shortEntryNprice[0], nQty, leverage, price_mult, qty_mult, scale_mult
            )
            nBalance[0] += _to_nPnl(
                nPrice,
                nQty,
                False,
                longEntryNprice[0],
                shortEntryNprice[0],
                price_mult,
                qty_mult,
                scale_mult,
            )
            shortNqty[0] -= nQty

        if not shortNqty[0]:
            shortEntryNprice[0] = 0

    if (not longNqty[0]) and (not shortNqty[0]) and (not obRow[0]):
        lockedNbalance[0] = 0


@njit(cache=True)
def _to_nMargin(
    nPrice: int,
    nQty: int,
    leverage: int,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
) -> int:
    margin: float = ((nQty / qty_mult) * (nPrice / price_mult)) / leverage
    return round(margin * scale_mult)


@njit(cache=True)
def _to_nPnl(
    closeNprice: int,
    nQty: int,
    is_long: bool,
    longEntryNprice: int,
    shortEntryNprice: int,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
) -> int:
    entryNprice: int = longEntryNprice if is_long else shortEntryNprice
    diffNprice: int = (closeNprice - entryNprice) * (1 if is_long else -1)
    pnl: float = (diffNprice / price_mult) * (nQty / qty_mult)
    return round(pnl * scale_mult)


@njit(cache=True)
def _to_unrealized_nPnl(
    trade_nPrice: int,
    unrealizedNpnl: memoryview,
    longUnrealizedNpnl: memoryview,
    shortUnrealizedNpnl: memoryview,
    longNqty: memoryview,
    shortNqty: memoryview,
    longEntryNprice: memoryview,
    shortEntryNprice: memoryview,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
) -> int:
    if longNqty[0]:
        longUnrealizedNpnl[0] = _to_nPnl(
            trade_nPrice,
            longNqty[0],
            True,
            longEntryNprice[0],
            shortEntryNprice[0],
            price_mult,
            qty_mult,
            scale_mult,
        )
    else:
        longUnrealizedNpnl[0] = 0

    if shortNqty[0]:
        shortUnrealizedNpnl[0] = _to_nPnl(
            trade_nPrice,
            shortNqty[0],
            False,
            longEntryNprice[0],
            shortEntryNprice[0],
            price_mult,
            qty_mult,
            scale_mult,
        )
    else:
        shortUnrealizedNpnl[0] = 0

    unrealizedNpnl[0] = longUnrealizedNpnl[0] + shortUnrealizedNpnl[0]
    return unrealizedNpnl[0]
