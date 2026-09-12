"""Risk management rules, order size calculations, and order ID encoding."""

from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

from imprint._core import constant as c
from imprint._core.account.base import Base


@dataclass(slots=True)
class RiskManagement(Base, ABC):
    """Risk management evaluator for position sizing, balance limits, and TP/SL order params.

    Attributes
    ----------
    time_for_expired_signal : int
        Maximum allowed time window in milliseconds for signal execution.
    """

    __entry_qty: int = field(init=False)
    __tp_dev: int = field(init=False)
    __sl_dev: int = field(init=False)
    __max_lock_balance: int = field(init=False)
    __max_loss_balance: int = field(init=False)
    __min_order_size: int = field(init=False)
    time_for_expired_signal: int = field(init=False)
    __tp_offset_for_order_id: int = field(default=1_000_000_000, init=False)
    __sl_offset_for_order_id: int = field(default=2_000_000_000, init=False)

    @override
    def __post_init__(self) -> None:
        """Initialize risk thresholds, order sizing limits, and signal timers."""
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
        """Check if current balance remains above the maximum loss threshold.

        Returns
        -------
        bool
            True if balance loss is within tolerable limit, False otherwise.
        """

        return self.nBalance[0] > (
            self.startNbalance
            - (self.startNbalance * self.__max_loss_balance // 10_000)
        )

    @final
    @property
    def lockedNbalanceSafeLimit(self) -> bool:
        """Check if locked balance remains below the maximum margin lock limit.

        Returns
        -------
        bool
            True if locked margin is below threshold, False otherwise.
        """

        return self.lockedNbalance[0] < (
            self.nBalance[0] * self.__max_lock_balance // 10_000
        )

    @final
    @property
    def nominalEntryNqty(self) -> int:
        """Calculate unleveraged position entry allocation in scaled fixed-point units.

        Returns
        -------
        int
            Unleveraged entry amount in scale fixed-point units.
        """

        return self.availableNbalance[0] * self.__entry_qty // 10_000

    @final
    @property
    def nominalEntryNqtyWithLeverage(self) -> int | None:
        """Calculate leveraged position entry allocation if above minimum order threshold.

        Returns
        -------
        int or None
            Leveraged entry amount in scale units, or None if below min_order_size.
        """

        if (
            qty := (self.leverage * self.nominalEntryNqty)
        ) > self.__min_order_size:
            return qty

    @final
    def entryNqtyWithLeverage(self, nPrice: int, nominalNqty: int) -> int:
        """Calculate asset quantity in fixed-point integer units for entry price.

        Parameters
        ----------
        nPrice : int
            Asset entry price in fixed-point integer format.
        nominalNqty : int
            Nominal margin allocation in scale fixed-point format.

        Returns
        -------
        int
            Target quantity in integer fixed-point units.
        """

        nominal_qty: float = nominalNqty / self.scale_mult
        return round((nominal_qty * self.price_mult * self.qty_mult) / nPrice)

    @final
    def tp_sl_param(
        self, nPrice: int, client_order_id: int, is_long: bool, is_tp: bool
    ) -> tuple[int, int, int]:
        """Calculate target execution price, bitmask flags, and client order ID for TP/SL.

        Parameters
        ----------
        nPrice : int
            Base entry price in fixed-point integer format.
        client_order_id : int
            Base client order identifier.
        is_long : bool
            True for long position, False for short.
        is_tp : bool
            True to construct Take Profit parameters, False for Stop Loss.

        Returns
        -------
        tuple of (int, int, int)
            Tuple containing (nPrice_with_dev, order_param_bitmask, encoded_client_order_id).
        """
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
        """Convert generic or SL order ID to Take Profit order ID range.

        Parameters
        ----------
        id : int
            Raw or encoded client order ID.

        Returns
        -------
        int
            Client order ID with TP offset applied.
        """
        if self.is_tp_client_order_id(id):
            return id
        else:
            if self.is_sl_client_order_id(id):
                return (
                    id - self.__sl_offset_for_order_id
                ) + self.__tp_offset_for_order_id
            else:
                return id + self.__tp_offset_for_order_id

    def to_sl_client_order_id(self, id: int) -> int:
        """Convert generic or TP order ID to Stop Loss order ID range.

        Parameters
        ----------
        id : int
            Raw or encoded client order ID.

        Returns
        -------
        int
            Client order ID with SL offset applied.
        """
        if self.is_sl_client_order_id(id):
            return id
        else:
            if self.is_tp_client_order_id(id):
                return (
                    id - self.__tp_offset_for_order_id
                ) + self.__sl_offset_for_order_id
            else:
                return id + self.__sl_offset_for_order_id

    def is_tp_client_order_id(self, id: int) -> bool:
        """Check if client order ID falls within Take Profit ID range.

        Parameters
        ----------
        id : int
            Client order identifier.

        Returns
        -------
        bool
            True if order ID is a Take Profit order, False otherwise.
        """
        return (
            self.__tp_offset_for_order_id <= id < self.__sl_offset_for_order_id
        )

    def is_sl_client_order_id(self, id: int) -> bool:
        """Check if client order ID falls within Stop Loss ID range.

        Parameters
        ----------
        id : int
            Client order identifier.

        Returns
        -------
        bool
            True if order ID is a Stop Loss order, False otherwise.
        """
        return self.__sl_offset_for_order_id <= id
