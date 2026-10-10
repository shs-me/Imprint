from datetime import UTC, datetime

from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.account.position import JitPosition
from imprint._vis.settings import CloseTrades, OpenTrades


def analyze_orders_history(
    start_balance: float,
    leverage: int,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    orders: NDArray[int64],
) -> tuple[list[CloseTrades], list[OpenTrades], list[float], int, float, float]:
    price_mult_: memoryview = memoryview(bytearray(8)).cast("q")
    qty_mult_: memoryview = memoryview(bytearray(8)).cast("q")
    scale_mult_: memoryview = memoryview(bytearray(8)).cast("q")
    leverage_: memoryview = memoryview(bytearray(8)).cast("q")

    price_mult_[0], qty_mult_[0] = price_mult, qty_mult
    scale_mult_[0], leverage_[0] = scale_mult, leverage

    nBalance: memoryview = memoryview(bytearray(8)).cast("q")
    lockedNbalance: memoryview = memoryview(bytearray(8)).cast("q")
    longNqty: memoryview = memoryview(bytearray(8)).cast("q")
    longEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")
    shortNqty: memoryview = memoryview(bytearray(8)).cast("q")
    shortEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")
    long_mae: memoryview = memoryview(bytearray(8)).cast("q")
    long_mfe: memoryview = memoryview(bytearray(8)).cast("q")
    short_mae: memoryview = memoryview(bytearray(8)).cast("q")
    short_mfe: memoryview = memoryview(bytearray(8)).cast("q")

    pos = JitPosition(
        price_mult=price_mult_,
        qty_mult=qty_mult_,
        scale_mult=scale_mult_,
        leverage=leverage_,
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
        unrealizedNpnl=memoryview(bytearray(8)).cast("q"),
        longUnrealizedNpnl=memoryview(bytearray(8)).cast("q"),
        shortUnrealizedNpnl=memoryview(bytearray(8)).cast("q"),
    )

    trades_close: list[CloseTrades] = []
    trades_open: list[OpenTrades] = []
    all_pnls: list[float] = []

    sum_commission: float = 0
    turnover: float = 0

    nBalance[0] = round(start_balance * scale_mult)
    ohRow: int = orders.shape[0]

    for row in range(ohRow):
        nPrice: int = int(orders[row, c.TP_nPrice])
        nQty: int = int(orders[row, c.TP_nQty])
        timestamp: int = int(orders[row, c.TP_timestamp])
        orderParam: int = int(orders[row, c.TP_order_param])
        nCommission: int = int(orders[row, c.TP_nCommission])
        nMAE: int = int(orders[row, c.TP_nMAE])
        nMFE: int = int(orders[row, c.TP_nMFE])
        planned_sl: int = int(orders[row, c.TP_planned_sl])
        planned_tp: int = int(orders[row, c.TP_planned_tp])

        is_filled: bool = bool(orderParam & c.OF_FILLED)
        is_maker: bool = bool(orderParam & c.OF_LIMIT)
        is_long: bool = bool(orderParam & c.OF_LONG)
        is_buy: bool = bool(orderParam & c.OF_BUY)
        is_open: bool = (is_buy and is_long) or (not is_buy and not is_long)

        if is_filled:
            sum_commission += nCommission / scale_mult
            dt: datetime = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
            price: float = nPrice / price_mult
            qty: float = nQty / qty_mult
            turnover += price * qty

            if is_open:
                pos.update_position(
                    nPrice, nQty, is_long, is_open, is_maker, nCommission
                )
                trades_open.append(
                    {
                        "time": dt,
                        "balance": nBalance[0] / scale_mult,
                        "price": price,
                        "is_long": is_long,
                        "is_buy": is_buy,
                    }
                )
            else:
                if is_long:
                    nPnl = pos.to_long_nPnl(nPrice, longEntryNprice[0], nQty)
                else:
                    nPnl = pos.to_short_nPnl(nPrice, shortEntryNprice[0], nQty)

                pnl: float = nPnl / scale_mult

                entry_p: float = (
                    longEntryNprice[0] if is_long else shortEntryNprice[0]
                ) / price_mult

                pnl_pct: float = (
                    ((price - entry_p) if is_long else (entry_p - price))
                    / entry_p
                    * 100.0
                )

                mae: float = nMAE / scale_mult
                mae_pct: float = -abs(mae / (entry_p * qty) * 100.0)

                mfe: float = nMFE / scale_mult
                mfe_pct: float = abs(mfe / (entry_p * qty) * 100.0)

                all_pnls.append(pnl)
                pos.update_position(
                    nPrice, nQty, is_long, is_open, is_maker, nCommission
                )
                trades_close.append(
                    {
                        "time": dt,
                        "color": "green" if pnl > 0 else "red",
                        "is_long": is_long,
                        "balance": nBalance[0] / scale_mult,
                        "price": price,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "mae": mae,
                        "mae_pct": mae_pct,
                        "mfe": mfe,
                        "mfe_pct": mfe_pct,
                        "planned_tp_pct": planned_tp / 10_000 * 100,
                        "planned_sl_pct": -(planned_sl / 10_000 * 100),
                    }
                )

    return (
        trades_close,
        trades_open,
        all_pnls,
        nBalance[0],
        sum_commission,
        turnover,
    )
