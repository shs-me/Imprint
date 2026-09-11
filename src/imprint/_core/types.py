from multiprocessing import Process
from typing import Any, Protocol, TypedDict, overload


class ExecutionProtocol(Protocol):
    def on_signal(
        self,
        signal_id: int,
        time_get_signal: int,
        order_param: int,
        nPrice: int,
        nQty: int,
    ) -> None: ...
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
    ) -> None: ...
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
    ) -> None: ...


class LoggerProtocol(Protocol):
    @overload
    def info(__self, __message: str, *args: Any, **kwargs: Any) -> None: ...  # noqa: PYI063
    @overload
    def info(__self, __message: Any) -> None: ...  # noqa: PYI063
    @overload
    def success(__self, __message: str, *args: Any, **kwargs: Any) -> None: ...  # noqa: PYI063
    @overload
    def success(__self, __message: Any) -> None: ...  # noqa: PYI063
    @overload
    def warning(__self, __message: str, *args: Any, **kwargs: Any) -> None: ...  # noqa: PYI063
    @overload
    def warning(__self, __message: Any) -> None: ...  # noqa: PYI063
    @overload
    def error(__self, __message: str, *args: Any, **kwargs: Any) -> None: ...  # noqa: PYI063
    @overload
    def error(__self, __message: Any) -> None: ...  # noqa: PYI063


class SendOrderMethodSignature(Protocol):
    def __call__(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None: ...


class SetLogMethodSignature(Protocol):
    def __call__(self, log: str) -> None: ...


class DumpMSG(TypedDict):
    timestamp: str
    type: str
    message: str
    traceback: list[str]
    locals: dict[str, Any]


class ProcsData(TypedDict):
    """Typed dictionary representing managed worker process state and metadata."""

    proc_name: str
    task_id: int
    proc: Process
