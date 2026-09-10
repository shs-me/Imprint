from collections.abc import Iterator
from typing import override

from msgspec import Struct

from imprint.configs import AggTradesDecoder


class BinanceAggTrade(Struct):
    p: str
    q: str
    T: int
    m: bool


class BinanceAggTradesDecoder(AggTradesDecoder[BinanceAggTrade]):
    @override
    def decode_agg_trade(
        self, msg: BinanceAggTrade
    ) -> Iterator[tuple[float, float, int, int]]:
        yield float(msg.p), float(msg.q), msg.T, 1 if msg.m else 0
