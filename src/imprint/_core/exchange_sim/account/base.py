from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.account.base import Base


@dataclass(slots=True)
class Account(Base, ABC):
    """Abstract base account managing balances, commissions, and order history logs.

    Attributes
    ----------
    takerNcommission : int
        Fixed taker commission rate in exchange units.
    makerNcommission : int
        Fixed maker commission rate in exchange units.
    orders_history : ndarray of shape (N, TP_ConstantCount)
        Preallocated contiguous array tracking historical order events and metrics.
    ohWid : memoryview
        Single-element integer memoryview acting as an append-only row cursor for ``orders_history``.
    oh_rows : int
        Allocation chunk size for resizing ``orders_history`` when capacity is exceeded.
    oh_cols : int
        Number of feature columns per order history record (matches ``TP_ConstantCount``).
    """

    takerNcommission: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    makerNcommission: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    orders_history: NDArray[int64] = field(
        default_factory=lambda: np.zeros(
            (10_000, c.TP_ConstantCount), dtype=int64
        ),
        init=False,
    )
    ohWid: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    oh_rows: int = field(default=10_000, init=False)
    oh_cols: int = field(default=c.TP_ConstantCount, init=False)

    @override
    def init(self) -> None:
        Base.init(self)

        cfgAC = self.manager.cfgAccount
        self.takerNcommission[0] = cfgAC.taker_commission.fixed
        self.makerNcommission[0] = cfgAC.maker_commission.fixed

    @override
    def reset(self) -> None:
        Base.reset(self)

        self.orders_history.fill(0)
        self.ohWid[0] = 0

    @final
    def lock_balance(self, nPrice: int, nQty: int, order_param: int) -> None:
        """Lock required margin for active limit orders based on side and position flags.

        Parameters
        ----------
        nPrice : int
            Normalized order limit price. Must be strictly positive.
        nQty : int
            Normalized order quantity. Must be strictly positive.
        order_param : int
            Bitmask containing order flags (e.g., ``OF_LONG``, ``OF_BUY``, ``OF_LIMIT``).
        """
        is_long: bool = bool(order_param & c.OF_LONG)
        is_buy: bool = bool(order_param & c.OF_BUY)
        if ((is_buy and is_long) or (not is_long and not is_buy)) and bool(
            order_param & c.OF_LIMIT
        ):
            self.lockedNbalance[0] += to_nMargin(
                nPrice=nPrice,
                nQty=nQty,
                leverage=self.leverage[0],
                price_mult=self.price_mult[0],
                qty_mult=self.qty_mult[0],
                scale_mult=self.scale_mult[0],
            )

        self.post_lock_balance()

    @abstractmethod
    def post_lock_balance(self) -> None:
        """Execute account-specific post-processing logic after margin locking."""

    @final
    def update_orders_history(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
        nMAE: int = 0,
        nMFE: int = 0,
        planned_tp: int = 0,
        planned_sl: int = 0,
    ) -> None:
        """Record an order event into the history log buffer, resizing dynamically if full.

        Parameters
        ----------
        timestamp : int
            Epoch timestamp of the order event in microseconds.
        order_param : int
            Bitmask describing order properties and flags.
        order_id : int
            Unique exchange-assigned order identifier.
        client_order_id : int
            Client-assigned order identifier.
        nPrice : int
            Normalized execution or placement price.
        nQty : int
            Normalized order quantity.
        nCommission : int
            Normalized commission assessed for the order execution in exchange units.
        nMAE : int, default=0
            Maximum Adverse Excursion in normalized price units.
        nMFE : int, default=0
            Maximum Favorable Excursion in normalized price units.
        planned_tp : int, default=0
            Planned take-profit target price level in normalized price units.
        planned_sl : int, default=0
            Planned stop-loss trigger price level in normalized price units.
        """
        ohWid, oh = self.ohWid, self.orders_history
        # - - -
        oh[ohWid[0], c.TP_timestamp] = timestamp
        oh[ohWid[0], c.TP_order_param] = order_param
        oh[ohWid[0], c.TP_order_id] = order_id
        oh[ohWid[0], c.TP_client_order_id] = client_order_id
        oh[ohWid[0], c.TP_nPrice] = nPrice
        oh[ohWid[0], c.TP_nQty] = nQty
        oh[ohWid[0], c.TP_nCommission] = nCommission
        oh[ohWid[0], c.TP_nMAE] = nMAE
        oh[ohWid[0], c.TP_nMFE] = nMFE
        oh[ohWid[0], c.TP_planned_tp] = planned_tp
        oh[ohWid[0], c.TP_planned_sl] = planned_sl
        ohWid[0] += 1
        if ohWid[0] >= oh.shape[0]:
            old_rows: int = oh.shape[0]
            self.orders_history = np.resize(
                oh, new_shape=((old_rows + self.oh_rows), self.oh_cols)
            )
            self.orders_history[old_rows:, :] = 0

    @final
    def save_orders_history(self) -> None:
        """Flush active non-zero order history logs to disk via NumPy binary format."""
        np.save(
            c.ORDERS_HISTORY_DATA_PATH,
            self.orders_history[: self.ohWid[0], :],
        )


@njit(cache=True)
def to_nMargin(
    nPrice: int,
    nQty: int,
    leverage: int,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
) -> int:
    """Compute required normalized margin for an open position or order.

    Parameters
    ----------
    nPrice : int
        Normalized asset price. Must be strictly positive.
    nQty : int
        Normalized asset quantity. Must be strictly positive.
    leverage : int
        Account leverage multiplier. Must be strictly positive.
    price_mult : int
        Scaling factor used to denormalize price. Must be strictly positive.
    qty_mult : int
        Scaling factor used to denormalize quantity. Must be strictly positive.
    scale_mult : int
        Scaling factor used to re-normalize the resulting margin value. Must be strictly positive.

    Returns
    -------
    int
        Rounded normalized margin requirement in integer units.
    """
    margin: float = ((nQty / qty_mult) * (nPrice / price_mult)) / leverage
    return round(margin * scale_mult)
