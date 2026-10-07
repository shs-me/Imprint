from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import override

import numba as nb
from numba import types  # pyright: ignore[reportPrivateImportUsage]
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import int64

from imprint._core.exchange_sim.account.base import Account, to_nMargin


@dataclass(slots=True)
class Position(Account, ABC):
    """Represent trading account positions, unrealized PnL, and MFE/MAE metrics.

    Attributes
    ----------
    longNqty : memoryview of shape (1,)
        Normalized quantity of the open long position.
    longEntryNprice : memoryview of shape (1,)
        Normalized volume-weighted average entry price for the long position.
    shortNqty : memoryview of shape (1,)
        Normalized quantity of the open short position.
    shortEntryNprice : memoryview of shape (1,)
        Normalized volume-weighted average entry price for the short position.
    unrealizedNpnl : memoryview of shape (1,)
        Total normalized unrealized PnL across all open positions.
    longUnrealizedNpnl : memoryview of shape (1,)
        Normalized unrealized PnL for the long position.
    shortUnrealizedNpnl : memoryview of shape (1,)
        Normalized unrealized PnL for the short position.
    long_mae : memoryview of shape (1,)
        Maximum adverse excursion (MAE) for the long position in normalized currency units.
    long_mfe : memoryview of shape (1,)
        Maximum favorable excursion (MFE) for the long position in normalized currency units.
    short_mae : memoryview of shape (1,)
        Maximum adverse excursion (MAE) for the short position in normalized currency units.
    short_mfe : memoryview of shape (1,)
        Maximum favorable excursion (MFE) for the short position in normalized currency units.
    """

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

    position: JitPosition = field(init=False)

    def __post_init__(self) -> None:
        Account.__post_init__(self)

        self.position = JitPosition(
            price_mult=self.price_mult,
            qty_mult=self.qty_mult,
            scale_mult=self.scale_mult,
            leverage=self.leverage,
            nBalance=self.nBalance,
            lockedNbalance=self.lockedNbalance,
            longNqty=self.longNqty,
            longEntryNprice=self.longEntryNprice,
            shortNqty=self.shortNqty,
            shortEntryNprice=self.shortEntryNprice,
            long_mae=self.long_mae,
            long_mfe=self.long_mfe,
            short_mae=self.short_mae,
            short_mfe=self.short_mfe,
            unrealizedNpnl=self.unrealizedNpnl,
            longUnrealizedNpnl=self.longUnrealizedNpnl,
            shortUnrealizedNpnl=self.shortUnrealizedNpnl,
        )

        print(self.position)

    @override
    def post_init(self) -> None:
        Account.post_init(self)

        self.position.price_mult = self.price_mult
        self.position.qty_mult = self.qty_mult
        self.position.scale_mult = self.scale_mult
        self.position.leverage = self.leverage
        self.position.nBalance = self.nBalance

    @override
    def reset(self) -> None:
        Account.reset(self)

        self.longNqty[0], self.longEntryNprice[0], self.shortNqty[0] = 0, 0, 0
        self.shortEntryNprice[0], self.unrealizedNpnl[0] = 0, 0
        self.longUnrealizedNpnl[0], self.shortUnrealizedNpnl[0] = 0, 0
        self.long_mae[0], self.long_mfe[0] = 0, 0
        self.short_mae[0], self.short_mfe[0] = 0, 0


spec = [
    ("price_mult", nb.int64),
    ("qty_mult", nb.int64),
    ("scale_mult", nb.int64),
    ("leverage", nb.int64),
    ("nBalance", types.MemoryView(nb.int64, 1, "C")),
    ("lockedNbalance", types.MemoryView(nb.int64, 1, "C")),
    ("longNqty", types.MemoryView(nb.int64, 1, "C")),
    ("longEntryNprice", types.MemoryView(nb.int64, 1, "C")),
    ("shortNqty", types.MemoryView(nb.int64, 1, "C")),
    ("shortEntryNprice", types.MemoryView(nb.int64, 1, "C")),
    ("long_mae", types.MemoryView(nb.int64, 1, "C")),
    ("long_mfe", types.MemoryView(nb.int64, 1, "C")),
    ("short_mae", types.MemoryView(nb.int64, 1, "C")),
    ("short_mfe", types.MemoryView(nb.int64, 1, "C")),
    ("unrealizedNpnl", types.MemoryView(nb.int64, 1, "C")),
    ("longUnrealizedNpnl", types.MemoryView(nb.int64, 1, "C")),
    ("shortUnrealizedNpnl", types.MemoryView(nb.int64, 1, "C")),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue,reportUntypedClassDecorator]
class JitPosition:
    """Manage JIT-compiled exchange position state, order fills, and risk metrics.

    Parameters
    ----------
    price_mult : int
        Multiplier used for price precision normalization.
    qty_mult : int
        Multiplier used for quantity precision normalization.
    scale_mult : int
        Multiplier used for monetary scaling.
    leverage : int
        Account leverage ratio.
    nBalance : memoryview of shape (1,)
        Normalized account balance.
    lockedNbalance : memoryview of shape (1,)
        Normalized margin balance locked in open positions.
    longNqty : memoryview of shape (1,)
        Normalized quantity of the open long position.
    longEntryNprice : memoryview of shape (1,)
        Normalized volume-weighted average entry price for the long position.
    shortNqty : memoryview of shape (1,)
        Normalized quantity of the open short position.
    shortEntryNprice : memoryview of shape (1,)
        Normalized volume-weighted average entry price for the short position.
    long_mae : memoryview of shape (1,)
        Maximum adverse excursion (MAE) for the long position in normalized currency units.
    long_mfe : memoryview of shape (1,)
        Maximum favorable excursion (MFE) for the long position in normalized currency units.
    short_mae : memoryview of shape (1,)
        Maximum adverse excursion (MAE) for the short position in normalized currency units.
    short_mfe : memoryview of shape (1,)
        Maximum favorable excursion (MFE) for the short position in normalized currency units.
    unrealizedNpnl : memoryview of shape (1,)
        Total normalized unrealized PnL across all open positions.
    longUnrealizedNpnl : memoryview of shape (1,)
        Normalized unrealized PnL for the long position.
    shortUnrealizedNpnl : memoryview of shape (1,)
        Normalized unrealized PnL for the short position.

    Attributes
    ----------
    price_mult : int
        Multiplier used for price precision normalization.
    qty_mult : int
        Multiplier used for quantity precision normalization.
    scale_mult : int
        Multiplier used for monetary scaling.
    leverage : int
        Account leverage ratio.
    nBalance : memoryview of shape (1,)
        Normalized account balance.
    lockedNbalance : memoryview of shape (1,)
        Normalized margin balance locked in open positions.
    longNqty : memoryview of shape (1,)
        Normalized quantity of the open long position.
    longEntryNprice : memoryview of shape (1,)
        Normalized volume-weighted average entry price for the long position.
    shortNqty : memoryview of shape (1,)
        Normalized quantity of the open short position.
    shortEntryNprice : memoryview of shape (1,)
        Normalized volume-weighted average entry price for the short position.
    long_mae : memoryview of shape (1,)
        Maximum adverse excursion (MAE) for the long position in normalized currency units.
    long_mfe : memoryview of shape (1,)
        Maximum favorable excursion (MFE) for the long position in normalized currency units.
    short_mae : memoryview of shape (1,)
        Maximum adverse excursion (MAE) for the short position in normalized currency units.
    short_mfe : memoryview of shape (1,)
        Maximum favorable excursion (MFE) for the short position in normalized currency units.
    unrealizedNpnl : memoryview of shape (1,)
        Total normalized unrealized PnL across all open positions.
    longUnrealizedNpnl : memoryview of shape (1,)
        Normalized unrealized PnL for the long position.
    shortUnrealizedNpnl : memoryview of shape (1,)
        Normalized unrealized PnL for the short position.
    """

    def __init__(
        self,
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
        unrealizedNpnl: memoryview,
        longUnrealizedNpnl: memoryview,
        shortUnrealizedNpnl: memoryview,
    ) -> None:
        self.price_mult: int = price_mult
        self.qty_mult: int = qty_mult
        self.scale_mult: int = scale_mult
        self.leverage: int = leverage
        self.nBalance: memoryview = nBalance
        self.lockedNbalance: memoryview = lockedNbalance
        self.longNqty: memoryview = longNqty
        self.longEntryNprice: memoryview = longEntryNprice
        self.shortNqty: memoryview = shortNqty
        self.shortEntryNprice: memoryview = shortEntryNprice
        self.long_mae: memoryview = long_mae
        self.long_mfe: memoryview = long_mfe
        self.short_mae: memoryview = short_mae
        self.short_mfe: memoryview = short_mfe
        self.unrealizedNpnl: memoryview = unrealizedNpnl
        self.longUnrealizedNpnl: memoryview = longUnrealizedNpnl
        self.shortUnrealizedNpnl: memoryview = shortUnrealizedNpnl

    def update_position(
        self,
        nPrice: int,
        nQty: int,
        is_long: bool,
        is_open: bool,
        is_maker: bool,
        nCommission: int,
    ) -> None:
        """Update position state, entry price, balance, and locked margin from an order fill.

        Parameters
        ----------
        nPrice : int
            Normalized fill price.
        nQty : int
            Normalized fill quantity.
        is_long : bool
            True if the fill pertains to a long position, false for short.
        is_open : bool
            True if opening or increasing a position, false if reducing or closing.
        is_maker : bool
            True if the fill is a liquidity maker (incurring zero margin lock when opening).
        nCommission : int
            Normalized commission deducted from balance.
        """
        self.nBalance[0] -= nCommission
        if is_open and not is_maker:
            self.lockedNbalance[0] += self.to_nMargin(nPrice, nQty)

        if is_long:
            self._update_long_position(
                nPrice=nPrice, nQty=nQty, is_open=is_open
            )
        else:
            self._update_short_position(
                nPrice=nPrice, nQty=nQty, is_open=is_open
            )

    def _update_long_position(
        self, nPrice: int, nQty: int, is_open: bool
    ) -> None:
        """Update long position quantity, volume-weighted entry price, and realized PnL.

        Parameters
        ----------
        nPrice : int
            Normalized fill price.
        nQty : int
            Normalized fill quantity.
        is_open : bool
            True if opening or increasing the long position, false if closing.
        """
        if is_open:
            if self.longNqty[0]:
                self.longEntryNprice[0] = (
                    (self.longEntryNprice[0] * self.longNqty[0])
                    + (nPrice * nQty)
                ) // (self.longNqty[0] + nQty)
            else:
                self.longEntryNprice[0] = nPrice

            self.longNqty[0] += nQty
        else:
            self.lockedNbalance[0] -= self.to_nMargin(
                self.longEntryNprice[0], nQty
            )
            self.nBalance[0] += self.to_long_nPnl(
                closeNprice=nPrice,
                entryNprice=self.longEntryNprice[0],
                nQty=nQty,
            )
            self.longNqty[0] -= nQty

        if not self.longNqty[0]:
            self.longEntryNprice[0], self.long_mae[0], self.long_mfe[0] = (
                0,
                0,
                0,
            )

    def _update_short_position(
        self, nPrice: int, nQty: int, is_open: bool
    ) -> None:
        """Update short position quantity, volume-weighted entry price, and realized PnL.

        Parameters
        ----------
        nPrice : int
            Normalized fill price.
        nQty : int
            Normalized fill quantity.
        is_open : bool
            True if opening or increasing the short position, false if closing.
        """
        if is_open:
            if self.shortNqty[0]:
                self.shortEntryNprice[0] = (
                    (self.shortEntryNprice[0] * self.shortNqty[0])
                    + (nPrice * nQty)
                ) // (self.shortNqty[0] + nQty)
            else:
                self.shortEntryNprice[0] = nPrice

            self.shortNqty[0] += nQty
        else:
            self.lockedNbalance[0] -= self.to_nMargin(
                self.shortEntryNprice[0], nQty
            )
            self.nBalance[0] += self.to_short_nPnl(
                closeNprice=nPrice,
                entryNprice=self.shortEntryNprice[0],
                nQty=nQty,
            )
            self.shortNqty[0] -= nQty

        if not self.shortNqty[0]:
            self.shortEntryNprice[0], self.short_mae[0], self.short_mfe[0] = (
                0,
                0,
                0,
            )

    def update_unrealized_nPnl(self, nPrice: int) -> int:
        """Calculate and update unrealized PnL for both long and short positions at current market price.

        Parameters
        ----------
        nPrice : int
            Current normalized market price.

        Returns
        -------
        int
            Updated total normalized unrealized PnL.
        """
        self._update_long_unrealized_nPnl(nPrice=nPrice)
        self._update_short_unrealized_nPnl(nPrice=nPrice)
        self.unrealizedNpnl[0] = (
            self.longUnrealizedNpnl[0] + self.shortUnrealizedNpnl[0]
        )
        return self.unrealizedNpnl[0]

    def _update_long_unrealized_nPnl(self, nPrice: int) -> None:
        """Calculate and update unrealized PnL for the open long position.

        Parameters
        ----------
        nPrice : int
            Current normalized market price.
        """
        if self.longNqty[0]:
            self.longUnrealizedNpnl[0] = self.to_long_nPnl(
                closeNprice=nPrice,
                entryNprice=self.longEntryNprice[0],
                nQty=self.longNqty[0],
            )
        else:
            self.longUnrealizedNpnl[0] = 0

    def _update_short_unrealized_nPnl(self, nPrice: int) -> None:
        """Calculate and update unrealized PnL for the open short position.

        Parameters
        ----------
        nPrice : int
            Current normalized market price.
        """
        if self.shortNqty[0]:
            self.shortUnrealizedNpnl[0] = self.to_short_nPnl(
                closeNprice=nPrice,
                entryNprice=self.shortEntryNprice[0],
                nQty=self.shortNqty[0],
            )
        else:
            self.shortUnrealizedNpnl[0] = 0

    def update_mae_and_mfe(self) -> None:
        """Update maximum adverse excursion (MAE) and maximum favorable excursion (MFE) metrics for positions."""
        self._update_long_mae_and_mfe()
        self._update_short_mae_and_mfe()

    def _update_long_mae_and_mfe(self) -> None:
        """Update MAE and MFE tracking values for the long position."""
        self.long_mae[0] = min(self.longUnrealizedNpnl[0], self.long_mae[0])
        self.long_mfe[0] = max(self.longUnrealizedNpnl[0], self.long_mfe[0])

    def _update_short_mae_and_mfe(self) -> None:
        """Update MAE and MFE tracking values for the short position."""
        self.short_mae[0] = min(self.shortUnrealizedNpnl[0], self.short_mae[0])
        self.short_mfe[0] = max(self.shortUnrealizedNpnl[0], self.short_mfe[0])

    def to_nMargin(self, nPrice: int, nQty: int) -> int:
        """Compute required normalized margin for an open position or order.

        Parameters
        ----------
        nPrice : int
            Normalized asset price.
        nQty : int
            Normalized asset quantity.

        Returns
        -------
        int
            Rounded normalized margin requirement in integer units.
        """
        return to_nMargin(
            nPrice=nPrice,
            nQty=nQty,
            leverage=self.leverage,
            price_mult=self.price_mult,
            qty_mult=self.qty_mult,
            scale_mult=self.scale_mult,
        )

    def to_long_nPnl(
        self, closeNprice: int | int64, entryNprice: int, nQty: int | int64
    ) -> int:
        """Calculate normalized PnL for a long position fill or closure.

        Parameters
        ----------
        closeNprice : int | int64
            Normalized exit or close price.
        entryNprice : int
            Normalized average entry price.
        nQty : int | int64
            Normalized quantity being closed.

        Returns
        -------
        int
            Normalized PnL in currency units.
        """
        diffNprice: int | int64 = (closeNprice - entryNprice) * 1
        pnl: float = (diffNprice / self.price_mult) * (nQty / self.qty_mult)
        return round(pnl * self.scale_mult)

    def to_short_nPnl(
        self, closeNprice: int | int64, entryNprice: int, nQty: int | int64
    ) -> int:
        """Calculate normalized PnL for a short position fill or closure.

        Parameters
        ----------
        closeNprice : int | int64
            Normalized exit or close price.
        entryNprice : int
            Normalized average entry price.
        nQty : int | int64
            Normalized quantity being closed.

        Returns
        -------
        int
            Normalized PnL in currency units.
        """
        diffNprice: int | int64 = (closeNprice - entryNprice) * -1
        pnl: float = (diffNprice / self.price_mult) * (nQty / self.qty_mult)
        return round(pnl * self.scale_mult)
