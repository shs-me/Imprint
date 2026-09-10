from collections.abc import Iterator
from typing import override

from msgspec import Struct

from imprint.configs import AggTradesDecoder


class BybitAggTrade(Struct):
    p: str
    v: str
    T: int
    S: str


class BybitTradeMsg(Struct):
    topic: str
    data: list[BybitAggTrade]


class BybitAggTradesDecoder(AggTradesDecoder[BybitTradeMsg]):
    @override
    def decode_agg_trade(
        self, msg: BybitTradeMsg
    ) -> Iterator[tuple[float, float, int, int]]:
        for t in msg.data:
            is_sell = 1 if (t.S.upper() == "SELL") else 0
            yield float(t.p), float(t.v), t.T, is_sell
