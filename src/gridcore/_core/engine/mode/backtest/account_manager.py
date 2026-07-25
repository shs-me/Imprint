import time
from datetime import datetime

import numpy as np
from numba import njit
from numpy import int64, uint8
from numpy.typing import NDArray

from ..... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from . import matching_engine as me

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


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

        cfgFP = manager.cfgFootprint
        self.timeframe: int = int(cfgFP.timeframe)
        start_dt: datetime = datetime.fromisoformat(
            manager.cfgSetup.backtest_start_date
        )
        end_dt: datetime = datetime.fromisoformat(manager.cfgSetup.backtest_end_date)
        total_days: int = max(1, (end_dt - start_dt).days + 1)
        self.bar_count: int = (total_days * 24 * 60 * 60 * 1000) // self.timeframe

        self.equity_history: NDArray[int64] = np.zeros(
            (self.bar_count, EquityC + 1), dtype=int64
        )

        self.base_timestamp: memoryview = memoryview(bytearray(8)).cast("q")

        self.nBalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.lockedNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.availableNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.dynamicNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.longNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self.longEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")

        self.unrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.longUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.long_mae: memoryview = memoryview(bytearray(8)).cast("q")
        self.long_mfe: memoryview = memoryview(bytearray(8)).cast("q")
        self.short_mae: memoryview = memoryview(bytearray(8)).cast("q")
        self.short_mfe: memoryview = memoryview(bytearray(8)).cast("q")

        self.nBalance[0] = self.startNbalance
        self.availableNbalance[0] = self.startNbalance
        self.dynamicNbalance[0] = self.startNbalance

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
            self.dynamicNbalance,
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
            self.timeframe,
            self.equity_history,
            self.base_timestamp,
            self.long_mae,
            self.long_mfe,
            self.short_mae,
            self.short_mfe,
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
            if bool(order_param & c.OF_LIMIT):
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

    # Agent Methods
    def final_action(self) -> None:
        self.dump_equity_history()

    def dump_equity_history(self) -> None:
        valid_mask = self.equity_history[:, 0] > 0
        np.save(c.EQUITY_HISTORY_DUMP_PATH, self.equity_history[valid_mask])


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
        memoryview,
        int,
        int,
        int,
        memoryview,
        int,
        int,
        NDArray[int64],
        memoryview,
        memoryview,
        memoryview,
        memoryview,
        memoryview,
    ],
) -> bool:
    time_readed_trade, dfm, dfmRid, dfmWid = args[0:4]
    order_book, obRow, order_id_buf = args[4:7]
    data_buf, data_buf_size, data_header, data_example, deRow = args[7:12]
    slippage, latency, leverage, makerNcommission, takerNcommission = args[12:17]
    nBalance, lockedNbalance, availableNbalance, dynamicNbalance = args[17:21]
    unrealizedNpnl, longUnrealizedNpnl, shortUnrealizedNpnl = args[21:24]
    longNqty, longEntryNprice, shortNqty, shortEntryNprice = args[24:28]
    price_mult, qty_mult, scale_mult = args[28:31]
    writer_id, cell_amount = args[31:33]
    timeframe, equity_history, base_timestamp = args[33:36]
    long_mae, long_mfe, short_mae, short_mfe = args[36:40]

    max_row: int = dfm.shape[0]
    while time_readed_trade[0] < timestamp:
        row: int = dfmRid[0]

        if row == dfmWid[0]:
            return False

        new_row: int = row + 1
        dfmRid[0] = new_row if (new_row < max_row) else 0

        trade_nPrice: int = dfm[row, 0]
        trade_timestamp: int = dfm[row, 1]
        time_readed_trade[0] = trade_timestamp

        uNpnl = _update_unrealized_nPnl(
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
            long_mae=long_mae,
            long_mfe=long_mfe,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )
        dynamicNbalance[0] = nBalance[0] + uNpnl
        availableNbalance[0] = dynamicNbalance[0] - lockedNbalance[0]

        _update_equity_ohlc(
            trade_timestamp=trade_timestamp,
            current_equity=dynamicNbalance[0],
            equity_history=equity_history,
            base_timestamp=base_timestamp,
            timeframe=timeframe,
        )

        if obRow[0] == 0:
            continue

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
                long_mae=long_mae,
                long_mfe=long_mfe,
                short_mae=short_mae,
                short_mfe=short_mfe,
            )

        uNpnl = _update_unrealized_nPnl(
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
            long_mae=long_mae,
            long_mfe=long_mfe,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )
        dynamicNbalance[0] = nBalance[0] + uNpnl
        availableNbalance[0] = dynamicNbalance[0] - lockedNbalance[0]

        _update_equity_ohlc(
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
def _update_unrealized_nPnl(
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
    long_mae: memoryview,
    long_mfe: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> int:
    if longNqty[0] or shortNqty[0]:
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
            if longUnrealizedNpnl[0] < long_mae[0]:
                long_mae[0] = longUnrealizedNpnl[0]
            if longUnrealizedNpnl[0] > long_mfe[0]:
                long_mfe[0] = longUnrealizedNpnl[0]
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
            if shortUnrealizedNpnl[0] < short_mae[0]:
                short_mae[0] = shortUnrealizedNpnl[0]
            if shortUnrealizedNpnl[0] > short_mfe[0]:
                short_mfe[0] = shortUnrealizedNpnl[0]
        else:
            shortUnrealizedNpnl[0] = 0
    else:
        longUnrealizedNpnl[0], shortUnrealizedNpnl[0] = 0, 0

    unrealizedNpnl[0] = longUnrealizedNpnl[0] + shortUnrealizedNpnl[0]
    return unrealizedNpnl[0]


@njit(cache=True)
def _update_equity_ohlc(
    trade_timestamp: int,
    current_equity: int,
    equity_history: NDArray[int64],
    base_timestamp: memoryview,
    timeframe: int,
) -> None:
    ce, eh = current_equity, equity_history
    # - - -
    if base_timestamp[0] == 0:
        base_timestamp[0] = trade_timestamp - (trade_timestamp % timeframe)

    bar: int = (trade_timestamp - base_timestamp[0]) // timeframe
    max_bars: int = equity_history.shape[0]

    if 0 <= bar < max_bars:
        if equity_history[bar, EquityT] == 0:
            bar_open_time: int = base_timestamp[0] + (bar * timeframe)
            eh[bar, :] = bar_open_time, ce, ce, ce, ce

            prev_bar: int = bar - 1
            while prev_bar >= 0 and equity_history[prev_bar, 0] == 0:
                eh[prev_bar, EquityT] = base_timestamp[0] + (prev_bar * timeframe)
                eh[prev_bar, EquityO:] = ce, ce, ce, ce
                prev_bar -= 1
        else:
            if current_equity > equity_history[bar, EquityH]:
                equity_history[bar, EquityH] = current_equity
            if current_equity < equity_history[bar, EquityL]:
                equity_history[bar, EquityL] = current_equity
            equity_history[bar, EquityC] = current_equity


@njit(cache=True)
def _update_positions(
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
    long_mae: memoryview,
    long_mfe: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> None:
    max_de_row: int = deRow[0]
    for de_row in range(max_de_row):
        deRow[0] -= 1
        trade_timestamp, order_param, order_id, nPrice, nQty, nCommission, mae, mfe = (
            data_example[de_row, :]
        )

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

            _update_position(
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
    is_maker: bool,
    nCommission: int,
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
    nBalance[0] -= nCommission
    if is_open and not is_maker:
        lockedNbalance[0] += _to_nMargin(
            nPrice,
            nQty,
            leverage,
            price_mult,
            qty_mult,
            scale_mult,
        )

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
            longEntryNprice[0], long_mae[0], long_mfe[0] = 0, 0, 0

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
            shortEntryNprice[0], short_mae[0], short_mfe[0] = 0, 0, 0


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
