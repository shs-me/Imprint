from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import final, override

from imprint._core.account import Account
from imprint._core.types import (
    ExecutionProtocol,
    SendOrderMethodSignature,
    SetLogMethodSignature,
)


@dataclass(slots=True)
class ExecutionEngine(ExecutionProtocol, ABC):
    """Abstract router managing backtest and live execution agents.

    Routes execution events and states between a pipeline's node manager and the
    appropriate underlying backtest or live execution agent."""

    is_backtesting: bool
    count_open_positions: memoryview
    account: Account
    send_order: SendOrderMethodSignature
    logger: SetLogMethodSignature

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
        """Process an inbound trading signal and route it for execution."""

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
        """Handle execution notification for a completely filled order."""

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
        """Handle cancellation notification for a pending order."""

    @override
    def reset(self) -> None: ...
