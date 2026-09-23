from multiprocessing import Process
from typing import Any, Protocol, TypedDict, overload

from numpy import int64


class AlgorithmProtocol(Protocol):
    tick_by_tick_analyze: bool
    atr_period: int
    park_period: int
    ma_volume_period: int
    ma_count_trade_period: int
    ma_avg_trade_size_period: int
    big_cluster_mult: float

    def on_clusters_update(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None: ...

    def on_bar_close(self) -> None: ...

    def on_bar_update(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None: ...


class ExecutionProtocol(Protocol):
    def on_signal(
        self,
        signal_id: int,
        time_get_signal: int,
        order_param: int,
        nPrice: int,
        nQty: int,
        tp_dev: int,
        sl_dev: int,
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
