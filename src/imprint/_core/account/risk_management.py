"""Risk management rules, order size calculations, and order ID encoding."""

from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

from imprint._core import constant as c
from imprint._core.account.base import Base
from imprint._core.ipc import NodeManager


@dataclass(slots=True)
class RiskManagement(Base, ABC):
    """Evaluate position sizing, balance limits, and take-profit/stop-loss order parameters.

    Attributes
    ----------
    time_for_expired_signal : int
        Maximum allowed time window in milliseconds for signal execution before expiration.
    """

    _long_tp_dev: int = field(default=0, init=False)
    _long_sl_dev: int = field(default=0, init=False)
    _short_tp_dev: int = field(default=0, init=False)
    _short_sl_dev: int = field(default=0, init=False)
    __entry_qty: int = field(init=False)
    __max_lock_balance: int = field(init=False)
    __max_loss_balance: int = field(init=False)
    __min_order_size: int = field(init=False)
    time_for_expired_signal: int = field(init=False)
    __tp_offset_for_order_id: int = field(default=1_000_000_000, init=False)
    __sl_offset_for_order_id: int = field(default=2_000_000_000, init=False)

    @override
    def post_init(self, manager: NodeManager) -> None:
        """Initialize risk thresholds, order sizing limits, and signal timers."""
        Base.post_init(self, manager)

        cfgAC = manager.cfgAccount
        self.__min_order_size = round(cfgAC.min_order_size * self.scale_mult)

        cfgRM = manager.cfgRiskManagement
        self.__entry_qty = cfgRM.entry_qty.fixed
        self.__max_lock_balance = cfgRM.max_lock_balance.fixed
        self.__max_loss_balance = cfgRM.max_loss_balance.fixed
        self.time_for_expired_signal = (
            cfgRM.pass_execute_signal_if_timer_ms_exepired
        )

    @final
    @property
    def lossNbalanceSafeLimit(self) -> bool:
        """Evaluate whether current normalized balance remains above the maximum loss threshold.

        Returns
        -------
        bool
            True if account balance loss is within the configured maximum limit, False otherwise.
        """

        return self.nBalance[0] > (
            self.startNbalance
            - (self.startNbalance * self.__max_loss_balance // 10_000)
        )

    @final
    @property
    def lockedNbalanceSafeLimit(self) -> bool:
        """Evaluate whether currently locked margin remains below the maximum margin lock limit.

        Returns
        -------
        bool
            True if locked margin is below the configured percentage of balance, False otherwise.
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
            Unleveraged entry amount in scaled fixed-point integer units.
        """

        return self.availableNbalance[0] * self.__entry_qty // 10_000

    @final
    @property
    def nominalEntryNqtyWithLeverage(self) -> int | None:
        """Calculate leveraged position entry allocation if above the minimum order size threshold.

        Returns
        -------
        int | None
            Leveraged entry amount in scaled fixed-point units, or None if below the minimum order size.
        """

        if (
            qty := (self.leverage * self.nominalEntryNqty)
        ) > self.__min_order_size:
            return qty

    @final
    def entryNqtyWithLeverage(self, nPrice: int, nominalNqty: int) -> int:
        """Calculate asset order quantity in fixed-point integer units for a given entry price and nominal allocation.

        Parameters
        ----------
        nPrice : int
            Asset entry price in fixed-point integer format.
        nominalNqty : int
            Nominal margin allocation in scaled fixed-point format.

        Returns
        -------
        int
            Target order quantity in integer fixed-point units.
        """

        nominal_qty: float = nominalNqty / self.scale_mult
        return round((nominal_qty * self.price_mult * self.qty_mult) / nPrice)

    @final
    def set_tp_sel_dev(self, tp: int, sl: int, order_param: int) -> None:
        """Configure take-profit and stop-loss deviation parameters for long or short positions.

        Parameters
        ----------
        tp : int
            Take-profit deviation in basis points (10,000 = 100%).
        sl : int
            Stop-loss deviation in basis points (10,000 = 100%).
        order_param : int
            Order parameter bitmask containing position direction flags (e.g., ``c.OF_LONG``).
        """
        if order_param & c.OF_LONG:
            self._long_tp_dev, self._long_sl_dev = tp, sl
        else:
            self._short_tp_dev, self._short_sl_dev = tp, sl

    @final
    def tp_sl_param(
        self, nPrice: int, client_order_id: int, is_long: bool, is_tp: bool
    ) -> tuple[int, int, int]:
        """Calculate target execution price, order parameter bitmask, and encoded client order ID for TP/SL.

        Parameters
        ----------
        nPrice : int
            Base entry price in fixed-point integer format.
        client_order_id : int
            Base client order identifier.
        is_long : bool
            True for long position, False for short position.
        is_tp : bool
            True to construct Take Profit parameters, False for Stop Loss.

        Returns
        -------
        tuple[int, int, int]
            Tuple containing ``(nPrice_with_dev, order_param_bitmask, encoded_client_order_id)``.
        """
        dev: int = (
            (self._long_tp_dev if is_tp else self._long_sl_dev)
            if is_long
            else (self._short_tp_dev if is_tp else self._short_sl_dev)
        )
        ticks: int = nPrice * dev // 10_000
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
        """Convert a generic or stop-loss client order ID into the Take Profit ID range.

        Parameters
        ----------
        id : int
            Raw, take-profit, or stop-loss encoded client order identifier.

        Returns
        -------
        int
            Client order identifier with Take Profit offset applied.
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
        """Convert a generic or take-profit client order ID into the Stop Loss ID range.

        Parameters
        ----------
        id : int
            Raw, take-profit, or stop-loss encoded client order identifier.

        Returns
        -------
        int
            Client order identifier with Stop Loss offset applied.
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
        """Determine whether a client order identifier falls within the Take Profit ID range.

        Parameters
        ----------
        id : int
            Client order identifier to evaluate.

        Returns
        -------
        bool
            True if the order ID is within the Take Profit range, False otherwise.
        """
        return (
            self.__tp_offset_for_order_id <= id < self.__sl_offset_for_order_id
        )

    def is_sl_client_order_id(self, id: int) -> bool:
        """Determine whether a client order identifier falls within the Stop Loss ID range.

        Parameters
        ----------
        id : int
            Client order identifier to evaluate.

        Returns
        -------
        bool
            True if the order ID is within the Stop Loss range, False otherwise.
        """
        return self.__sl_offset_for_order_id <= id
