from numba import njit

from .converter import to_nMargin, to_nPnl


@njit(cache=True)
def update_position(
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
        lockedNbalance[0] += to_nMargin(
            nPrice, nQty, leverage, price_mult, qty_mult, scale_mult
        )

    if is_long:
        update_long_position(
            nPrice=nPrice,
            nQty=nQty,
            is_open=is_open,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            leverage=leverage,
            nBalance=nBalance,
            lockedNbalance=lockedNbalance,
            longNqty=longNqty,
            longEntryNprice=longEntryNprice,
            shortEntryNprice=shortEntryNprice,
            long_mae=long_mae,
            long_mfe=long_mfe,
        )
    else:
        update_short_position(
            nPrice=nPrice,
            nQty=nQty,
            is_open=is_open,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            leverage=leverage,
            nBalance=nBalance,
            lockedNbalance=lockedNbalance,
            shortNqty=shortNqty,
            longEntryNprice=longEntryNprice,
            shortEntryNprice=shortEntryNprice,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )


@njit(cache=True)
def update_long_position(
    nPrice: int,
    nQty: int,
    is_open: bool,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    leverage: int,
    nBalance: memoryview,
    lockedNbalance: memoryview,
    longNqty: memoryview,
    longEntryNprice: memoryview,
    shortEntryNprice: memoryview,
    long_mae: memoryview,
    long_mfe: memoryview,
) -> None:
    if is_open:
        if longNqty[0]:
            longEntryNprice[0] = (
                (longEntryNprice[0] * longNqty[0]) + (nPrice * nQty)
            ) // (longNqty[0] + nQty)
        else:
            longEntryNprice[0] = nPrice

        longNqty[0] += nQty
    else:
        lockedNbalance[0] -= to_nMargin(
            longEntryNprice[0], nQty, leverage, price_mult, qty_mult, scale_mult
        )
        nBalance[0] += to_nPnl(
            nPrice,
            nQty,
            True,
            longEntryNprice[0],
            shortEntryNprice[0],
            price_mult,
            qty_mult,
            scale_mult,
        )
        longNqty[0] -= nQty

    if not longNqty[0]:
        longEntryNprice[0], long_mae[0], long_mfe[0] = 0, 0, 0


@njit(cache=True)
def update_short_position(
    nPrice: int,
    nQty: int,
    is_open: bool,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    leverage: int,
    nBalance: memoryview,
    lockedNbalance: memoryview,
    longEntryNprice: memoryview,
    shortNqty: memoryview,
    shortEntryNprice: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> None:
    if is_open:
        if shortNqty[0]:
            shortEntryNprice[0] = (
                (shortEntryNprice[0] * shortNqty[0]) + (nPrice * nQty)
            ) // (shortNqty[0] + nQty)
        else:
            shortEntryNprice[0] = nPrice

        shortNqty[0] += nQty
    else:
        lockedNbalance[0] -= to_nMargin(
            shortEntryNprice[0], nQty, leverage, price_mult, qty_mult, scale_mult
        )
        nBalance[0] += to_nPnl(
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
