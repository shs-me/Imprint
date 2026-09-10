from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.account.base import Base


@dataclass(slots=True)
class Account(Base, ABC):
    takerNcommission: int = field(init=False)
    makerNcommission: int = field(init=False)
    __save_orders_history: bool = field(init=False)

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
    def __post_init__(self) -> None:
        Base.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.takerNcommission = cfgAC.taker_commission.fixed
        self.makerNcommission = cfgAC.maker_commission.fixed
        self.__save_orders_history = cfgAC.save_orders_history

    @final
    def lock_balance(self, nPrice: int, nQty: int, order_param: int) -> None:
        is_long: bool = bool(order_param & c.OF_LONG)
        is_buy: bool = bool(order_param & c.OF_BUY)
        if ((is_buy and is_long) or (not is_long and not is_buy)) and bool(
            order_param & c.OF_LIMIT
        ):
            self.lockedNbalance[0] += to_nMargin(
                nPrice,
                nQty,
                self.leverage,
                self.price_mult,
                self.qty_mult,
                self.scale_mult,
            )

        self.post_lock_balance()

    @abstractmethod
    def post_lock_balance(self) -> None: ...

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
    ) -> None:
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
        ohWid[0] += 1
        if ohWid[0] >= oh.shape[0]:
            old_rows: int = oh.shape[0]
            self.orders_history = np.resize(
                oh, new_shape=((old_rows + self.oh_rows), self.oh_cols)
            )
            self.orders_history[old_rows:, :] = 0

    @final
    def save_orders_history(self) -> None:
        """Flushes non-zero order history logs to disk."""

        if self.__save_orders_history:
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
    margin: float = ((nQty / qty_mult) * (nPrice / price_mult)) / leverage
    return round(margin * scale_mult)
