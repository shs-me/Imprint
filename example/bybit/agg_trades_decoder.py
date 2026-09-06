from collections.abc import Iterator
from typing import override

from msgspec import Struct
from msgspec.json import Decoder

from imprint.api.setup import AggTradesDecoder


class BybitAggTrade(Struct):
    p: str
    v: str
    T: int
    S: str


class BybitTradeMsg(Struct):
    topic: str
    data: list[BybitAggTrade]


class BybitAggTradesDecoder(AggTradesDecoder):
    @override
    def __post_init__(self) -> None:
        self.decoder: Decoder[BybitTradeMsg] = Decoder(
            type=BybitTradeMsg, strict=False
        )

    @override
    def decode(
        self, raw_data: memoryview
    ) -> Iterator[tuple[float, float, int, int]]:
        msg = self.decoder.decode(raw_data)
        for t in msg.data:
            is_sell = 1 if (t.S.upper() == "SELL") else 0
            yield float(t.p), float(t.v), t.T, is_sell
