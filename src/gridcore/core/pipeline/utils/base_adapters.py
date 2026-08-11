from abc import ABC, abstractmethod

from msgspec.structs import Struct


class AggTrades(Struct):
    def price(self) -> float:
        raise NotImplementedError

    def qty(self) -> float:
        raise NotImplementedError

    def timestamp(self) -> int:
        raise NotImplementedError

    def is_sell(self) -> bool:
        raise NotImplementedError


class UserStreamDecoder(ABC):
    @abstractmethod
    def decode_user_event(self, raw_json: bytes) -> bytes | None:
        """return @8q or None"""
        pass


class OrderEncoder(ABC):
    @abstractmethod
    def encode_order_request(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> bytes:
        pass
