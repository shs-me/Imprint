import struct
from typing import override

import msgspec

from imprint.api import constant as c
from imprint.api.base import UserStreamDecoder


class BinanceUserStreamDecoder(UserStreamDecoder):
    @override
    def __post_init__(self) -> None:
        self.decoder = msgspec.json.Decoder()

    @override
    def decode_user_event(self, raw_json: bytes) -> bytes | None:
        data = self.decoder.decode(raw_json)
        event_type = data.get("e")

        if event_type == "ORDER_TRADE_UPDATE":
            o = data["o"]
            timestamp = int(data["E"])
            order_id = int(o["i"])
            nPrice = round(float(o["p"]) * self.price_mult)
            nQty = round(float(o["q"]) * self.qty_mult)
            nCommission = round(float(o.get("n", 0)) * self.scale_mult)

            order_param = 0
            order_param |= c.OF_LONG if o["S"] == "BUY" else c.OF_SHORT
            order_param |= c.OF_BUY if o["S"] == "BUY" else c.OF_SELL
            order_param |= c.OF_LIMIT if o["o"] == "LIMIT" else c.OF_MARKET

            status = o["X"]
            if status == "NEW":
                order_param |= c.OF_NEW
            elif status in ("FILLED", "PARTIALLY_FILLED"):
                order_param |= c.OF_FILLED
            elif status == "CANCELED":
                order_param |= c.OF_CANCELED

            return struct.pack(
                "@qqqqqqqq",
                timestamp,
                1,
                order_param,
                order_id,
                nPrice,
                nQty,
                nCommission,
                0,
            )

        elif event_type == "ACCOUNT_UPDATE":
            timestamp = int(data["E"])
            balances = data["a"]["B"]
            for b in balances:
                if b["a"] == "USDT":
                    nBalance = round(float(b["wb"]) * self.scale_mult)
                    return struct.pack(
                        "@qqqqqqqq",
                        timestamp,
                        2,
                        0,
                        0,
                        0,
                        0,
                        0,
                        nBalance,
                    )
        return None
