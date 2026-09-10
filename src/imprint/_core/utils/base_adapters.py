import hashlib
import hmac
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, TypeVar, final

from msgspec import DecodeError, EncodeError, ValidationError
from msgspec.json import Decoder, Encoder
from websockets import ClientConnection

from imprint._core.utils.base_rest import BaseREST

T = TypeVar("T")


class ApiNotFoundError(Exception): ...


@dataclass(slots=True)
class ExchangeREST(BaseREST, ABC):
    symbol: str = field(default="")

    recv_window: int = field(default=5000, init=False)

    __api_key: str | None = field(default=None, init=False, repr=False)
    __api_secret: str | None = field(default=None, init=False, repr=False)

    __symbol_data: tuple[str, str, float, int] | None = field(
        default=None, init=False
    )
    __tick_size: str | None = field(default=None, init=False)
    __lot_size: str | None = field(default=None, init=False)
    __min_order_size: float | None = field(default=None, init=False)
    __leverage: int | None = field(default=None, init=False)

    @final
    @property
    def tick_size(self) -> str:
        if self.__tick_size is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__tick_size = self.__symbol_data[0]
        return self.__tick_size

    @final
    @property
    def lot_size(self) -> str:
        if self.__lot_size is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__lot_size = self.__symbol_data[1]
        return self.__lot_size

    @final
    @property
    def min_order_size(self) -> float:
        if self.__min_order_size is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__min_order_size = self.__symbol_data[2]
        return self.__min_order_size

    @final
    @property
    def leverage(self) -> int:
        if self.__leverage is None:
            if self.__symbol_data is None:
                self.__symbol_data = self._fetch_symbol_data()
            self.__leverage = self.__symbol_data[3]
        return self.__leverage

    @final
    @property
    def api_key(self) -> str:
        if self.__api_key is None:
            if (api_key := os.getenv("API_KEY")) is None:
                raise ApiNotFoundError
            self.__api_key = api_key
        return self.__api_key

    @final
    @property
    def api_secret(self) -> str:
        if self.__api_secret is None:
            if (api_secret := os.getenv("API_SECRET")) is None:
                raise ApiNotFoundError
            self.__api_secret = api_secret
        return self.__api_secret

    @final
    def _sign_hmac_sha256(self, query_or_body: str) -> str:
        """Utility helper to generate HMAC SHA256 signature."""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_or_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @final
    def _get_timestamp_ms(self) -> int:
        """Returns current timestamp in milliseconds."""
        return int(time.time() * 1000)

    @abstractmethod
    def _fetch_symbol_data(self) -> tuple[str, str, float, int]: ...

    @abstractmethod
    def get_balance(self, asset: str = "USDT") -> float: ...

    @abstractmethod
    async def get_listen_key_async(self) -> str: ...

    @abstractmethod
    async def keep_listen_key_async(self, listen_key: str) -> bool: ...

    @abstractmethod
    async def close_listen_key_async(self, listen_key: str) -> bool: ...

    @abstractmethod
    def cancel_all_orders(self) -> bool: ...

    @abstractmethod
    def close_all_positions(self) -> bool: ...


@dataclass(slots=True)
class AggTradesDecoder[T](ABC):
    decoder: Decoder[T] = field(
        default_factory=lambda: Decoder(type=T), init=False
    )

    @final
    def decode(
        self, raw_data: memoryview
    ) -> Iterator[tuple[float, float, int, int]] | None:
        try:
            msg = self.decoder.decode(raw_data)
            return self.decode_agg_trade(msg)
        except DecodeError:
            return None

    @abstractmethod
    def decode_agg_trade(
        self, msg: T
    ) -> Iterator[tuple[float, float, int, int]]: ...


@dataclass(slots=True)
class OrderEncoder(ABC):
    rest: ExchangeREST

    encoder: Encoder = field(default_factory=lambda: Encoder(), init=False)

    @final
    def encode(self, data: Any) -> bytes | None:
        try:
            return self.encoder.encode(data)
        except EncodeError as e:
            return self.rest.log(f"Order data encode error: {e}")
        except ValidationError as e:
            return self.rest.log(f"Order data validation error: {e}")

    @abstractmethod
    def encode_new_order(
        self,
        timestamp: int,
        client_order_id: int,
        symbol: str,
        is_buy: bool,
        is_long: bool,
        is_market: bool,
        price: float,
        qty: float,
        time_in_force: str = "GTC",
    ) -> bytes | None: ...

    @abstractmethod
    def encode_cancel_order(
        self, symbol: str, client_order_id: int
    ) -> bytes | None: ...


@dataclass(slots=True)
class UserStreamDecoder[T](ABC):
    rest: ExchangeREST

    base_url: str

    price_mult: int
    qty_mult: int
    scale_mult: int

    decoder: Decoder[T] = field(
        default_factory=lambda: Decoder(type=T), init=False
    )

    @abstractmethod
    async def on_pre_connect(self) -> str: ...

    @abstractmethod
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @final
    def decode(self, raw_data: bytes | memoryview) -> bytes | None:
        try:
            return self.decode_user_event(raw_data)
        except DecodeError as e:
            return self.rest.log(f"User data decode error: {e}")

    @abstractmethod
    def decode_user_event(
        self, raw_data: bytes | memoryview
    ) -> bytes | None: ...
