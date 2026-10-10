from multiprocessing import Process
from typing import Any, Protocol, TypedDict, overload


class StrategyProtocol(Protocol):
    """Define the core algorithm execution and event callback interface.

    Attributes
    ----------
    tick_by_tick_analyze : bool
        Flag indicating whether to perform tick-by-tick analysis.
    atr_period : int
        Period length for Average True Range calculations. Must be positive.
    park_period : int
        Period length for Parkinson volatility calculations. Must be positive.
    ma_volume_period : int
        Period length for moving average volume smoothing. Must be positive.
    ma_count_trade_period : int
        Period length for moving average trade count calculations. Must be positive.
    ma_avg_trade_size_period : int
        Period length for moving average average trade size calculations. Must be positive.
    big_cluster_mult : float
        Multiplier threshold for identifying significant volume clusters. Must be
        greater than or equal to 1.0.
    """

    tick_by_tick_analyze: bool
    atr_period: int
    park_period: int
    ma_volume_period: int
    ma_count_trade_period: int
    ma_avg_trade_size_period: int
    big_cluster_mult: float

    def on_bar_update(
        self, idYmin: int, idYmax: int, idx: int, lidx: int
    ) -> None:
        """Handle real-time updates within the active bar timeframe.

        Parameters
        ----------
        idYmin : int
            Minimum price index bounding the active update region.
        idYmax : int
            Maximum price index bounding the active update region. Must be
            greater than or equal to ``idYmin``.
        idx : int
            Current price level index.
        lidx : int
            Last active price level index.
        """

    def on_bar_close(self, idx: int, lidx: int) -> None:
        """Handle completion and closure of the current time bar.

        Parameters
        ----------
        idx : int
            Terminal price level index at bar close.
        lidx : int
            Terminal last price level index at bar close.
        """

    def reset(self) -> None: ...


class ExecutionProtocol(Protocol):
    """Define trade execution callback interfaces for order lifecycle events."""

    def on_signal(
        self,
        signal_id: int,
        time_get_signal: int,
        order_param: int,
        nPrice: int,
        nQty: int,
        tp_dev: int,
        sl_dev: int,
    ) -> None:
        """Handle generation of a new trading signal.

        Parameters
        ----------
        signal_id : int
            Unique identifier of the generated signal.
        time_get_signal : int
            Epoch timestamp in milliseconds when the signal was generated.
        order_param : int
            Bitmask parameter flags governing order execution.
        nPrice : int
            Scaled integer price value for the target order. Must be positive.
        nQty : int
            Order quantity in base units. Must be positive.
        tp_dev : int
            Take-profit deviation offset in price ticks.
        sl_dev : int
            Stop-loss deviation offset in price ticks.
        """
        ...

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
            Epoch timestamp in milliseconds when the fill occurred.
        is_long : bool
            Flag indicating whether the underlying position direction is long.
        is_buy : bool
            Flag indicating whether the fill is a buy order.
        order_id : int
            Exchange-assigned unique order identifier.
        client_order_id : int
            Client-assigned unique order identifier.
        nPrice : int
            Scaled integer execution price. Must be positive.
        nQty : int
            Executed quantity in base units. Must be positive.
        nCommission : int
            Scaled integer commission fee assessed for the fill. Must be non-negative.
        """
        ...

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
        """Handle notification for an order cancellation.

        Parameters
        ----------
        timestamp : int
            Epoch timestamp in milliseconds when the cancellation occurred.
        is_long : bool
            Flag indicating whether the underlying position direction is long.
        is_buy : bool
            Flag indicating whether the canceled order was a buy.
        order_id : int
            Exchange-assigned unique order identifier.
        client_order_id : int
            Client-assigned unique order identifier.
        nPrice : int
            Scaled integer price of the canceled order. Must be positive.
        nQty : int
            Unexecuted quantity canceled in base units. Must be positive.
        nCommission : int
            Commission fee associated with the order state, if applicable. Must be non-negative.
        """
        ...

    def reset(self) -> None: ...


class LoggerProtocol(Protocol):
    """Define structured logging callback interfaces with overloaded signatures."""

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
    """Define callable signature for transmitting new order requests."""

    def __call__(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        """Transmit an order submission request.

        Parameters
        ----------
        timestamp : int
            Epoch timestamp in milliseconds when the order request was dispatched.
        order_param : int
            Bitmask parameter flags governing order routing and execution.
        client_order_id : int
            Client-assigned unique order identifier.
        nPrice : int
            Scaled integer target price. Must be positive.
        nQty : int
            Order quantity in base units. Must be positive.
        """
        ...


class SetLogMethodSignature(Protocol):
    """Define callable signature for logging messages."""

    def __call__(self, log: str) -> None:
        """Record a log message string.

        Parameters
        ----------
        log : str
            Formatted log message content to record.
        """
        ...


class DumpMSG(TypedDict):
    """Represent serialized debugging or error dump messages.

    Attributes
    ----------
    timestamp : str
        ISO-8601 formatted timestamp string representing when the dump was created.
    type : str
        Classification category of the dump or error event.
    message : str
        Primary description or payload of the error message.
    traceback : list[str]
        Stack trace lines captured at the point of exception or dump.
    locals : dict[str, Any]
        Local variable namespace and inspection state dictionary.
    """

    timestamp: str
    type: str
    message: str
    traceback: list[str]
    locals: dict[str, Any]


class ProcsData(TypedDict):
    """Represent managed worker process state and metadata.

    Attributes
    ----------
    proc_name : str
        Descriptive name or label identifying the worker process.
    task_id : int
        Unique integer identifier associated with the task assignment.
    proc : Process
        Underlying multiprocessing Process instance handle.
    """

    proc_name: str
    task_id: int
    proc: Process


class RunData(TypedDict):
    id: int
    symbol: str
    start_date: str
    end_date: str
    timeframe: int
    timeframe_name: str
    leverage: int
    price_mult: int
    qty_mult: int
    scale_mult: int
    start_balance: float
    end_balance: float
    net_profit: float
    count_trade_close: int
