from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field

from msgspec.json import Encoder


@dataclass
class AggTradesDecoder(ABC):
    @abstractmethod
    def __post_init__(self) -> None:
        pass

    @abstractmethod
    def decode(self, raw_data: memoryview) -> Iterator[tuple[float, float, int, int]]:
        pass


@dataclass
class UserStreamDecoder(ABC):
    price_mult: int
    qty_mult: int
    scale_mult: int

    @abstractmethod
    def __post_init__(self) -> None:
        pass

    @abstractmethod
    def decode_user_event(self, raw_json: bytes) -> bytes | None:
        """return @8q or None"""
        pass


@dataclass
class OrderEncoder(ABC):
    encoder: Encoder = field(init=False)

    @abstractmethod
    def __post_init__(self) -> None:
        pass

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
    ) -> bytes:
        pass

    @abstractmethod
    def encode_cancel_order(self, symbol: str, client_order_id: int) -> bytes:
        pass
