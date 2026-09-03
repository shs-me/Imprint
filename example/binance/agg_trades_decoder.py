from collections.abc import Iterator
from typing import override

from msgspec import Struct
from msgspec.json import Decoder

from imprint.api.base import AggTradesDecoder


class BinanceAggTrade(Struct):
    p: str
    q: str
    T: int
    m: bool


class BinanceAggTradesDecoder(AggTradesDecoder):
    @override
    def __post_init__(self) -> None:
        self.decoder: Decoder[BinanceAggTrade] = Decoder(
            type=BinanceAggTrade, strict=False
        )

    @override
    def decode(
        self, raw_data: memoryview
    ) -> Iterator[tuple[float, float, int, int]]:
        trade = self.decoder.decode(raw_data)
        yield float(trade.p), float(trade.q), trade.T, 1 if trade.m else 0
