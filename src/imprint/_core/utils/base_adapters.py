import hashlib
import hmac
import os
import time
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from typing import Literal, TypeVar, final, get_args, get_origin

import numpy as np
from msgspec import DecodeError
from msgspec.json import Decoder, Encoder
from numpy import int64
from numpy.typing import NDArray
from websockets import ClientConnection

import imprint._core.constant as c
from imprint._core.utils.base import TradesArray
from imprint._core.utils.base_rest import BaseREST

T = TypeVar("T")


class TradesLoadError(Exception):
    """Raised when historical trades load fails repeatedly."""


@dataclass(slots=True)
class TradesLoader(BaseREST, ABC):
    symbol: str = field(default="", init=False)
    price_mult: int = field(default=0, init=False)
    qty_mult: int = field(default=0, init=False)
    cur_date: date = field(init=False)
    start_date: date = field(init=False)
    end_date: date = field(init=False)
    date_str: str = field(default="", init=False)
    start_date_str: str = field(default="", init=False)
    end_date_str: str = field(default="", init=False)
    data_dir: str = field(default="", init=False)
    data_path: str = field(default="", init=False)
    data_manifest_path: str = field(default="", init=False)

    @final
    def __post_init__(self) -> None:
        """Initialize REST timeouts, date bounds, and filesystem manifest paths."""
        self.connect_timeout: float | None = 10.0
        self.read_timeout: float | None = None
        self.write_timeout: float | None = None
        self.pool_timeout: float | None = None

        self.data_dir = c.TRADES_DATA_PATH
        os.makedirs(self.data_dir, exist_ok=True)

    @final
    def _download(
        self,
        symbol: str,
        start_date_str: str,
        end_date_str: str,
        price_mult: int,
        qty_mult: int,
    ) -> None:
        self.symbol = symbol
        self.start_date_str = start_date_str
        self.end_date_str = end_date_str
        self.price_mult = price_mult
        self.qty_mult = qty_mult

        self.init_session()

        manifest: str = self.data_manifest
        err_counter: int = 0
        downloaded_days: list[str] = []
        while self.cur_date <= self.end_date:
            self.date_str = self.cur_date.isoformat()
            if self.date_str not in manifest:
                if (trades := self.prepare_trades()) is not None:
                    self._append_to_npz(trades)
                    downloaded_days.append(
                        f"{self.date_str}: {self.format_bytes(trades.nbytes)}"
                    )
                else:
                    if (err_counter := (err_counter + 1)) >= 3:
                        raise TradesLoadError()
                    else:
                        continue

            self.cur_date += timedelta(days=1)
            err_counter = 0

        if downloaded_days:
            self.log(f"Downloaded days: {downloaded_days}")

    def init_session(self) -> None:
        self.start_date = date.fromisoformat(self.start_date_str)
        self.end_date = date.fromisoformat(self.end_date_str)

        if self.end_date >= (today := datetime.now(tz=UTC).date()):
            self.end_date = today - timedelta(days=1)

        self.cur_date = self.start_date
        data_path: list[str] = [
            p for p in os.listdir(self.data_dir) if p == f"{self.symbol}.npz"
        ]
        self.data_path = f"{self.data_dir}/{data_path[0]}" if data_path else ""
        self.data_manifest_path = f"{self.data_dir}/{self.symbol}_manifest.txt"

    @property
    def data_manifest(self) -> str:
        """str: Content of the download tracking manifest file listing completed dates."""
        try:
            with open(self.data_manifest_path, mode="r") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    @data_manifest.setter
    def data_manifest(self, new_data: str) -> None:
        with open(self.data_manifest_path, mode="a") as f:
            f.write(f"{new_data},")

    @abstractmethod
    def prepare_trades(self) -> TradesArray | None: ...

    @final
    def _append_to_npz(self, trades: TradesArray) -> None:
        if self.data_path:
            buffer = BytesIO()
            np.save(buffer, trades)
            with zipfile.ZipFile(self.data_path, "a") as z:
                z.writestr(f"{self.date_str}.npy", buffer.getvalue())
        else:
            self.data_path = f"{self.data_dir}/{self.symbol}.npz"
            kwd: dict[str, NDArray[int64]] = {self.date_str: trades}
            np.savez(self.data_path, **kwd)  # pyright: ignore[reportArgumentType]

        self.data_manifest = self.date_str


class ApiNotFoundError(Exception):
    """Raised when required API credentials cannot be located in the environment."""


@dataclass(slots=True)
class ExchangeREST(BaseREST, ABC):
    """Provide an abstract base interface for exchange REST API clients.

    Parameters
    ----------
    symbol : str, default=""
        Trading pair symbol identifier (e.g., ``"BTCUSDT"``).

    Attributes
    ----------
    symbol : str
        Trading pair symbol identifier.
    recv_window : int
        Maximum allowed time offset in milliseconds for request validity, default 5000.
    tick_size : str
        Minimum price movement increment for the symbol, fetched lazily.
    lot_size : str
        Minimum quantity step size for the symbol, fetched lazily.
    min_order_size : float
        Minimum allowable order quantity for the symbol, fetched lazily.
    api_key : str
        API authentication key loaded from environment variables.
    api_secret : str
        API secret key loaded from environment variables.
    """

    symbol: str = field(default="")

    recv_window: int = field(default=5000, init=False)

    __api_key: str | None = field(default=None, init=False, repr=False)
    __api_secret: str | None = field(default=None, init=False, repr=False)

    __symbol_data: tuple[str, str, float] | None = field(
        default=None, init=False
    )
    __tick_size: str | None = field(default=None, init=False)
    __lot_size: str | None = field(default=None, init=False)
    __min_order_size: float | None = field(default=None, init=False)

    @final
    @property
    def tick_size(self) -> str:
        """Fetch or return the minimum price movement increment."""
        if self.__tick_size is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__tick_size = self.__symbol_data[0]
        return self.__tick_size

    @final
    @property
    def lot_size(self) -> str:
        """Fetch or return the minimum quantity step size."""
        if self.__lot_size is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__lot_size = self.__symbol_data[1]
        return self.__lot_size

    @final
    @property
    def min_order_size(self) -> float:
        """Fetch or return the minimum allowable order quantity."""
        if self.__min_order_size is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__min_order_size = self.__symbol_data[2]
        return self.__min_order_size

    @abstractmethod
    def _fetch_symbol_data(self) -> tuple[str, str, float]:
        """Fetch raw tick size, lot size, and minimum order size from the exchange.

        Returns
        -------
        tuple[str, str, float]
            A tuple containing tick size, lot size, and minimum order size.
        """

    @final
    @property
    def api_key(self) -> str:
        """Retrieve the API authentication key from environment variables."""
        if self.__api_key is None:
            self.__api_key = self.__get_key("API")
        return self.__api_key

    @final
    @property
    def api_secret(self) -> str:
        """Retrieve the API secret key from environment variables."""
        if self.__api_secret is None:
            self.__api_secret = self.__get_key("SECRET")
        return self.__api_secret

    @final
    def __get_key(self, key: Literal["API", "SECRET"]) -> str:
        """Load specified environment variable key.

        Parameters
        ----------
        key : {'API', 'SECRET'}
            Target key category prefix to load.

        Returns
        -------
        str
            The resolved environment variable string value.

        Raises
        ------
        ApiNotFoundError
            If the corresponding environment variable ``{key}_KEY`` is not set.
        """
        from dotenv import load_dotenv

        load_dotenv()
        if (var := os.getenv(key + "_KEY")) is None:
            raise ApiNotFoundError
        else:
            return var

    @final
    def _sign_hmac_sha256(self, query_or_body: str) -> str:
        """Generate an HMAC SHA256 cryptographic signature for payload verification.

        Parameters
        ----------
        query_or_body : str
            Query string or request body payload to sign.

        Returns
        -------
        str
            Hexadecimal signature digest string.
        """
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_or_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @final
    def _get_timestamp_ms(self) -> int:
        """Retrieve the current UTC system timestamp in milliseconds.

        Returns
        -------
        int
            Current epoch time in milliseconds.
        """
        return int(time.time() * 1000)

    @abstractmethod
    async def get_agg_trades(self, first_id: int, last_id: int) -> bytes:
        """Fetch aggregate trades within a specified ID range.

        Parameters
        ----------
        first_id : int
            Starting aggregate trade ID.
        last_id : int
            Ending aggregate trade ID.

        Returns
        -------
        bytes
            Raw HTTP response payload bytes.
        """

    @abstractmethod
    def get_balance(self, asset: str = "USDT") -> float:
        """Retrieve available account balance for a specific asset.

        Parameters
        ----------
        asset : str, default="USDT"
            Target asset symbol code.

        Returns
        -------
        float
            Available balance amount.
        """

    @abstractmethod
    def set_leverage(self, leverage: int) -> None:
        """Configure trading leverage multiplier for the account or symbol.

        Parameters
        ----------
        leverage : int
            Target leverage integer multiplier. Must be strictly positive.
        """

    @abstractmethod
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders for the active symbol.

        Returns
        -------
        bool
            True if all open orders were successfully canceled, False otherwise.
        """

    @abstractmethod
    def close_all_positions(self) -> bool:
        """Close all open positions for the active symbol.

        Returns
        -------
        bool
            True if all positions were successfully closed, False otherwise.
        """


@dataclass(slots=True)
class TradesDecoder[T](ABC):
    """Decode raw trade message buffers using msgspec.

    Attributes
    ----------
    decoder : msgspec.json.Decoder[T]
        Configured message decoder instance.
    """

    decoder: Decoder[T] = field(init=False)

    @final
    def __post_init__(self) -> None:
        """Initialize the message decoder from generic type annotations."""
        for base in getattr(self, "__orig_bases__", []):
            if issubclass(get_origin(base), TradesDecoder):
                args = get_args(base)
                if args:
                    self.decoder = Decoder(type=args[0])

    @final
    def decode(
        self, raw_data: memoryview
    ) -> Iterator[tuple[float, float, int, int, int]] | None:
        """Decode raw memoryview buffer into structured trades.

        Parameters
        ----------
        raw_data : memoryview
            Raw binary message buffer to decode.

        Returns
        -------
        Iterator[tuple[float, float, int, int, int]] | None
            An iterator over decoded trade tuples, or None if decoding fails.
        """
        try:
            msg = self.decoder.decode(raw_data)
            return self.decode_trade(msg)
        except DecodeError:
            return None

    @abstractmethod
    def decode_trade(
        self, msg: T
    ) -> Iterator[tuple[float, float, int, int, int]]:
        """Process decoded message object into standardized trade tuples.

        Parameters
        ----------
        msg : T
            Decoded message object.

        Returns
        -------
        Iterator[tuple[float, float, int, int, int]]
            Yields trade attribute tuples.
        """


@final
@dataclass(slots=True)
class OrderData:
    """Store raw fields associated with an order event.

    Attributes
    ----------
    timestamp : int
        Event epoch timestamp in milliseconds.
    order_param : int
        Order parameter bitmask or status code.
    order_id : int
        Exchange-assigned unique order identifier.
    client_order_id : int
        Client-assigned unique order identifier.
    nPrice : int
        Scaled integer price value.
    nQty : int
        Scaled integer quantity value.
    nCommission : int
        Scaled integer commission fee amount.
    """

    timestamp: int = 0
    order_param: int = 0
    order_id: int = 0
    client_order_id: int = 0
    nPrice: int = 0
    nQty: int = 0
    nCommission: int = 0


@final
@dataclass(slots=True)
class BalanceData:
    """Store raw fields associated with an account balance update event.

    Attributes
    ----------
    nBalance : int
        Scaled total account balance amount.
    lockedNbalance : int
        Scaled locked balance amount in orders.
    availableNbalance : int
        Scaled available balance amount for trading.
    """

    nBalance: int = 0
    lockedNbalance: int = 0
    availableNbalance: int = 0


@dataclass(slots=True)
class UserStreamDecoder[T_REST, T_DECODER](ABC):
    """Provide an abstract base interface for WebSocket user stream decoders.

    Parameters
    ----------
    rest : T_REST
        Associated REST client instance.
    base_url : str
        Target WebSocket connection endpoint URL.
    price_mult : int
        Multiplicative scaling factor for price quantization.
    qty_mult : int
        Multiplicative scaling factor for quantity quantization.
    scale_mult : int
        General multiplicative scaling factor.

    Attributes
    ----------
    rest : T_REST
        Associated REST client instance.
    base_url : str
        Target WebSocket connection endpoint URL.
    price_mult : int
        Multiplicative scaling factor for price quantization.
    qty_mult : int
        Multiplicative scaling factor for quantity quantization.
    scale_mult : int
        General multiplicative scaling factor.
    decoder : msgspec.json.Decoder[T_DECODER]
        Configured message decoder instance.
    order_data : OrderData
        Reusable order data buffer structure.
    balance_data : BalanceData
        Reusable balance data buffer structure.
    """

    rest: T_REST

    base_url: str

    price_mult: int
    qty_mult: int
    scale_mult: int

    decoder: Decoder[T_DECODER] = field(init=False)
    order_data: OrderData = field(
        default_factory=lambda: OrderData(), init=False
    )
    balance_data: BalanceData = field(
        default_factory=lambda: BalanceData(), init=False
    )

    @final
    def __post_init__(self) -> None:
        """Initialize message decoder from generic type parameters."""
        for base in getattr(self, "__orig_bases__", []):
            if issubclass(get_origin(base), UserStreamDecoder):
                args = get_args(base)
                if args:
                    self.decoder = Decoder(type=args[1])

    @abstractmethod
    async def on_pre_connect(self) -> str:
        """Execute prerequisite asynchronous tasks before opening the WebSocket connection.

        Returns
        -------
        str
            Authentication token or connection URI query string parameter.
        """

    @abstractmethod
    async def on_connection(self, ws: ClientConnection) -> None:
        """Manage active WebSocket connection lifecycle and event subscription loops.

        Parameters
        ----------
        ws : websockets.ClientConnection
            Active WebSocket client connection handle.
        """

    @abstractmethod
    def decode(
        self, raw_data: bytes | memoryview
    ) -> Iterator[OrderData | BalanceData]:
        """Decode raw binary message buffer into order or balance data structures.

        Parameters
        ----------
        raw_data : bytes | memoryview
            Incoming raw binary message payload.

        Returns
        -------
        Iterator[OrderData | BalanceData]
            Iterator yielding decoded update objects.
        """


@dataclass(slots=True)
class OrderEncoder[T_REST](ABC):
    """Provide an abstract base interface for encoding order messages.

    Parameters
    ----------
    symbol : str
        Trading pair symbol identifier.
    rest : T_REST
        Associated REST client instance.

    Attributes
    ----------
    symbol : str
        Trading pair symbol identifier.
    rest : T_REST
        Associated REST client instance.
    encoder : msgspec.json.Encoder
        Configured msgspec JSON encoder instance.
    """

    symbol: str
    rest: T_REST
    encoder: Encoder = field(default_factory=lambda: Encoder(), init=False)

    @abstractmethod
    async def on_connection(self, ws: ClientConnection) -> None:
        """Perform initialization routines upon establishing the WebSocket connection.

        Parameters
        ----------
        ws : websockets.ClientConnection
            Active WebSocket client connection handle.
        """

    @abstractmethod
    def encode_new_order(
        self,
        timestamp: int,
        client_order_id: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        price: float,
        qty: float,
        time_in_force: str = "GTC",
    ) -> bytes:
        """Encode a new limit or market order payload.

        Parameters
        ----------
        timestamp : int
            Request epoch timestamp in milliseconds.
        client_order_id : int
            Unique client-side order identifier.
        is_long : bool
            Position side indicator (True for long, False for short).
        is_buy : bool
            Order side indicator (True for buy/bid, False for sell/ask).
        is_market : bool
            Order type indicator (True for market order, False for limit order).
        price : float
            Order limit price.
        qty : float
            Order quantity.
        time_in_force : str, default="GTC"
            Time-in-force policy identifier (e.g., ``"GTC"``, ``"IOC"``, ``"FOK"``).

        Returns
        -------
        bytes
            Encoded binary message payload.
        """

    @abstractmethod
    def encode_market_trigger_order(
        self,
        timestamp: int,
        client_order_id: int,
        is_long: bool,
        is_buy: bool,
        price: float,
        qty: float,
        time_in_force: str = "GTC",
    ) -> bytes:
        """Encode a market trigger or stop-loss/take-profit order payload.

        Parameters
        ----------
        timestamp : int
            Request epoch timestamp in milliseconds.
        client_order_id : int
            Unique client-side order identifier.
        is_long : bool
            Position side indicator (True for long, False for short).
        is_buy : bool
            Order side indicator (True for buy/bid, False for sell/ask).
        price : float
            Trigger or limit price.
        qty : float
            Order quantity.
        time_in_force : str, default="GTC"
            Time-in-force policy identifier.

        Returns
        -------
        bytes
            Encoded binary message payload.
        """

    @abstractmethod
    def encode_cancel_order(self, client_order_id: int) -> bytes:
        """Encode an order cancellation message payload.

        Parameters
        ----------
        client_order_id : int
            Unique client-side order identifier of the order to cancel.

        Returns
        -------
        bytes
            Encoded binary message payload.
        """
