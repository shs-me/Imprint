from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from imprint._core.account import Account
from imprint._core.types import ExecutionProtocol, SendOrderMethodSignature


@dataclass(slots=True)
class ExecutionEngine(ExecutionProtocol, ABC):
    """Abstract router managing backtest and live execution agents.

    Routes execution events and states between a pipeline's node manager and the
    appropriate underlying backtest or live execution agent.

    Attributes
    ----------
    is_backtesting : bool
        True if the execution context is configured for backtesting.
    count_open_positions : memoryview
        Shared-memory view tracking open position counts across trading symbols.
    account : Account
        Trading account context managing balances, margin, and positions.
    send_order : SendOrderMethodSignature
        Callable handle mapped to the active agent's order transmission interface.
    """

    is_backtesting: bool = field(init=False)
    count_open_positions: memoryview = field(init=False)
    account: Account = field(init=False)
    send_order: SendOrderMethodSignature = field(init=False)

    @final
    def __post_init__(self) -> None:
        self.post_init()

    def post_init(self) -> None:
        """Execute custom post-initialization logic in concrete subclasses."""

    @abstractmethod
    @override
    def on_signal(
        self,
        signal_id: int,
        time_get_signal: int,
        order_param: int,
        nPrice: int,
        nQty: int,
        tp_dev: int = 0,
        sl_dev: int = 0,
    ) -> None:
        """Process an inbound trading signal and route it for execution.

        Parameters
        ----------
        signal_id : int
            Unique identifier of the generated trading signal.
        time_get_signal : int
            UNIX epoch timestamp in microseconds indicating when the signal was received.
        order_param : int
            Bitmask or packed integer representing strategy-specific order routing parameters.
        nPrice : int
            Target order price scaled by the asset's precision multiplier.
        nQty : int
            Target order quantity scaled by the asset's size multiplier.
        tp_dev : int, default=0
            Take-profit deviation offset from the entry price, scaled. Zero disables.
        sl_dev : int, default=0
            Stop-loss deviation offset from the entry price, scaled. Zero disables.
        """

    @abstractmethod
    @override
    def on_filled_order(
        self,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        """Handle execution notification for a completely or partially filled order.

        Parameters
        ----------
        timestamp : int
            UNIX epoch timestamp in microseconds of the execution report.
        is_long : bool
            True if the filled order pertains to a long portfolio position.
        is_buy : bool
            True if the transaction is a buy/long-entry or short-cover.
        order_id : int
            Broker-assigned unique identifier for the order.
        client_order_id : int
            Locally generated unique client-side identifier for tracking.
        nPrice : int
            Execution price per unit, scaled by the precision multiplier.
        nQty : int
            Executed quantity of units, scaled by the size multiplier.
        nCommission : int
            Transaction commission cost incurred, scaled by the currency precision multiplier.
        """

    @abstractmethod
    @override
    def on_canceled_order(
        self,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        """Handle cancellation notification for a pending order.

        Parameters
        ----------
        timestamp : int
            UNIX epoch timestamp in microseconds of the cancellation report.
        is_long : bool
            True if the canceled order pertains to a long portfolio position.
        is_buy : bool
            True if the transaction was a buy order.
        order_id : int
            Broker-assigned unique identifier for the order.
        client_order_id : int
            Locally generated unique client-side identifier for tracking.
        nPrice : int
            Last quoted price of the order before cancellation, scaled.
        nQty : int
            Remaining unfilled quantity canceled, scaled.
        nCommission : int
            Commission charges incurred prior to or during cancellation, scaled.
        """

    @override
    def reset(self) -> None: ...
