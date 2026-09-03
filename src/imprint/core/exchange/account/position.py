from abc import ABC
from dataclasses import dataclass, field

from numba import njit

from imprint.core.exchange.account.base import Base
from imprint.core.exchange.account.converter import (
    to_long_nPnl,
    to_nMargin,
    to_short_nPnl,
)


@dataclass
class Position(Base, ABC):
    longNqty: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    longEntryNprice: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    shortNqty: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    shortEntryNprice: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    unrealizedNpnl: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    longUnrealizedNpnl: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    shortUnrealizedNpnl: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    long_mae: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    long_mfe: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    short_mae: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    short_mfe: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )


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
        _update_long_position(
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
            long_mae=long_mae,
            long_mfe=long_mfe,
        )
    else:
        _update_short_position(
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
            shortEntryNprice=shortEntryNprice,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )


@njit(cache=True)
def _update_long_position(
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
        nBalance[0] += to_long_nPnl(
            closeNprice=nPrice,
            entryNprice=longEntryNprice[0],
            nQty=longNqty[0],
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )
        longNqty[0] -= nQty

    if not longNqty[0]:
        longEntryNprice[0], long_mae[0], long_mfe[0] = 0, 0, 0


@njit(cache=True)
def _update_short_position(
    nPrice: int,
    nQty: int,
    is_open: bool,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    leverage: int,
    nBalance: memoryview,
    lockedNbalance: memoryview,
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
            shortEntryNprice[0],
            nQty,
            leverage,
            price_mult,
            qty_mult,
            scale_mult,
        )
        nBalance[0] += to_short_nPnl(
            closeNprice=nPrice,
            entryNprice=shortEntryNprice[0],
            nQty=shortNqty[0],
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )
        shortNqty[0] -= nQty

    if not shortNqty[0]:
        shortEntryNprice[0], short_mae[0], short_mfe[0] = 0, 0, 0


@njit(cache=True)
def update_unrealized_nPnl(
    nPrice: int,
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
    _update_long_unrealized_nPnl(
        nPrice=nPrice,
        longUnrealizedNpnl=longUnrealizedNpnl,
        longNqty=longNqty,
        longEntryNprice=longEntryNprice,
        price_mult=price_mult,
        qty_mult=qty_mult,
        scale_mult=scale_mult,
    )
    _update_short_unrealized_nPnl(
        nPrice=nPrice,
        shortUnrealizedNpnl=shortUnrealizedNpnl,
        shortNqty=shortNqty,
        shortEntryNprice=shortEntryNprice,
        price_mult=price_mult,
        qty_mult=qty_mult,
        scale_mult=scale_mult,
    )
    unrealizedNpnl[0] = longUnrealizedNpnl[0] + shortUnrealizedNpnl[0]
    return unrealizedNpnl[0]


@njit(cache=True)
def _update_long_unrealized_nPnl(
    nPrice: int,
    longUnrealizedNpnl: memoryview,
    longNqty: memoryview,
    longEntryNprice: memoryview,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
) -> None:
    if longNqty[0]:
        longUnrealizedNpnl[0] = to_long_nPnl(
            closeNprice=nPrice,
            entryNprice=longEntryNprice[0],
            nQty=longNqty[0],
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )
    else:
        longUnrealizedNpnl[0] = 0


@njit(cache=True)
def _update_short_unrealized_nPnl(
    nPrice: int,
    shortUnrealizedNpnl: memoryview,
    shortNqty: memoryview,
    shortEntryNprice: memoryview,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
) -> None:
    if shortNqty[0]:
        shortUnrealizedNpnl[0] = to_short_nPnl(
            closeNprice=nPrice,
            entryNprice=shortEntryNprice[0],
            nQty=shortNqty[0],
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )
    else:
        shortUnrealizedNpnl[0] = 0


@njit(cache=True)
def update_mae_and_mfe(
    longUnrealizedNpnl: memoryview,
    shortUnrealizedNpnl: memoryview,
    long_mae: memoryview,
    long_mfe: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> None:
    _update_long_mae_and_mfe(
        longUnrealizedNpnl=longUnrealizedNpnl,
        long_mae=long_mae,
        long_mfe=long_mfe,
    )
    _update_short_mae_and_mfe(
        shortUnrealizedNpnl=shortUnrealizedNpnl,
        short_mae=short_mae,
        short_mfe=short_mfe,
    )


@njit(cache=True)
def _update_long_mae_and_mfe(
    longUnrealizedNpnl: memoryview,
    long_mae: memoryview,
    long_mfe: memoryview,
) -> None:
    if longUnrealizedNpnl[0] < long_mae[0]:
        long_mae[0] = longUnrealizedNpnl[0]
    if longUnrealizedNpnl[0] > long_mfe[0]:
        long_mfe[0] = longUnrealizedNpnl[0]


@njit(cache=True)
def _update_short_mae_and_mfe(
    shortUnrealizedNpnl: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> None:
    if shortUnrealizedNpnl[0] < short_mae[0]:
        short_mae[0] = shortUnrealizedNpnl[0]
    if shortUnrealizedNpnl[0] > short_mfe[0]:
        short_mfe[0] = shortUnrealizedNpnl[0]
