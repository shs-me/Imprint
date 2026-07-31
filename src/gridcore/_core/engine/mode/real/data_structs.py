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


class BinanceAggTrades(AggTrades):
    p: float
    q: float
    T: int
    m: bool

    def price(self) -> float:
        return self.p

    def qty(self) -> float:
        return self.q

    def timestamp(self) -> int:
        return self.T

    def is_sell(self) -> bool:
        return self.m
