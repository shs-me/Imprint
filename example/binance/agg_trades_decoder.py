from collections.abc import Iterator
from dataclasses import dataclass
from typing import override

from msgspec import Struct

from imprint.configs import AggTradesDecoder


class AggTrade(Struct):
    p: str
    q: str
    T: int
    m: bool
    a: int


BinanceAggTrade = AggTrade | list[AggTrade]


@dataclass(slots=True)
class BinanceAggTradesDecoder(AggTradesDecoder[BinanceAggTrade]):
    @override
    def decode_agg_trade(
        self, msg: BinanceAggTrade
    ) -> Iterator[tuple[float, float, int, int, int]]:
        if isinstance(msg, list):
            for t in msg:
                yield (float(t.p), float(t.q), t.T, 1 if t.m else 0, t.a)
        else:
            yield float(msg.p), float(msg.q), msg.T, 1 if msg.m else 0, msg.a
