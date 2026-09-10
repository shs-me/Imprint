from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

from imprint._core import constant as c
from imprint._core.account.base import Base


@dataclass(slots=True)
class RiskManagement(Base, ABC):
    __entry_qty: int = field(init=False)
    __tp_dev: int = field(init=False)
    __sl_dev: int = field(init=False)
    __max_lock_balance: int = field(init=False)
    __max_loss_balance: int = field(init=False)
    __min_order_size: int = field(init=False)
    time_for_expired_signal: int = field(init=False)

    tp_offset_for_order_id: int = field(default=1_000_000, init=False)
    sl_offset_for_order_id: int = field(default=2_000_000, init=False)

    @override
    def __post_init__(self) -> None:
        Base.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.__min_order_size = round(cfgAC.min_order_size * self.scale_mult)

        cfgRM = self.manager.cfgRiskManagement
        self.__entry_qty = cfgRM.entry_qty.fixed
        self.__tp_dev = cfgRM.tp_dev.fixed
        self.__sl_dev = cfgRM.sl_dev.fixed
        self.__max_lock_balance = cfgRM.max_lock_balance.fixed
        self.__max_loss_balance = cfgRM.max_loss_balance.fixed
        self.time_for_expired_signal = (
            cfgRM.pass_execute_signal_if_timer_ms_exepired
        )

    @final
    @property
    def lossNbalanceSafeLimit(self) -> bool:
        """Evaluates whether current balance remains above max tolerable loss threshold."""

        return self.nBalance[0] > (
            self.startNbalance
            - (self.startNbalance * self.__max_loss_balance // 10_000)
        )

    @final
    @property
    def lockedNbalanceSafeLimit(self) -> bool:
        """Evaluates whether locked margin remains below max margin lock threshold."""

        return self.lockedNbalance[0] < (
            self.nBalance[0] * self.__max_lock_balance // 10_000
        )

    @final
    @property
    def nominalEntryNqty(self) -> int:
        """Calculates unleveraged position entry allocation in scale fixed-point units."""

        return self.availableNbalance[0] * self.__entry_qty // 10_000

    @final
    @property
    def nominalEntryNqtyWithLeverage(self) -> int | None:
        """Calculates leveraged entry size if above minimum order threshold."""

        if (
            qty := (self.leverage * self.nominalEntryNqty)
        ) > self.__min_order_size:
            return qty

    @final
    def entryNqtyWithLeverage(self, nPrice: int, nominalNqty: int) -> int:
        """Calculates target asset quantity int for specified entry price and nominal margin amount."""

        nominal_qty: float = nominalNqty / self.scale_mult
        return round((nominal_qty * self.price_mult * self.qty_mult) / nPrice)

    @final
    def tp_sl_param(
        self, nPrice: int, client_order_id: int, is_long: bool, is_tp: bool
    ) -> tuple[int, int, int]:
        ticks: int = (
            nPrice * (self.__tp_dev if is_tp else self.__sl_dev) // 10_000
        )
        ticks = (
            (ticks if is_tp else -ticks)
            if is_long
            else (-ticks if is_tp else ticks)
        )
        nPrice_with_dev: int = nPrice + ticks
        order_param: int = 0
        order_param |= c.OF_LONG if is_long else c.OF_SHORT
        order_param |= c.OF_SELL if is_long else c.OF_BUY
        order_param |= (c.OF_LIMIT if is_tp else c.OF_MARKET_TRIGGER) | c.OF_NEW
        client_order_id = (
            self.to_tp_client_order_id(client_order_id)
            if is_tp
            else self.to_sl_client_order_id(client_order_id)
        )
        return nPrice_with_dev, order_param, client_order_id

    def to_tp_client_order_id(self, id: int) -> int:
        if self.is_tp_client_order_id(id):
            return id
        else:
            if self.is_sl_client_order_id(id):
                return (
                    id - self.sl_offset_for_order_id
                ) + self.tp_offset_for_order_id
            else:
                return id + self.tp_offset_for_order_id

    def to_sl_client_order_id(self, id: int) -> int:
        if self.is_sl_client_order_id(id):
            return id
        else:
            if self.is_tp_client_order_id(id):
                return (
                    id - self.tp_offset_for_order_id
                ) + self.sl_offset_for_order_id
            else:
                return id + self.sl_offset_for_order_id

    def is_tp_client_order_id(self, id: int) -> bool:
        return self.tp_offset_for_order_id <= id < self.sl_offset_for_order_id

    def is_sl_client_order_id(self, id: int) -> bool:
        return self.sl_offset_for_order_id <= id
