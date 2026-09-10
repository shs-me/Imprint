import asyncio
import struct
from asyncio import Task
from dataclasses import dataclass, field
from typing import Any, override

from websockets import ClientConnection

from imprint import constant as c
from imprint._core.utils.base_rest import RestResponseError
from imprint.configs import UserStreamDecoder


@dataclass(slots=True)
class BinanceUserStreamDecoder(UserStreamDecoder[dict[str, Any]]):
    keep_task: Task[None] | None = field(default=None, init=False)

    @override
    async def on_pre_connect(self) -> str:
        listen_key: str = await self.rest.get_listen_key_async()

        if self.keep_task and not self.keep_task.done():
            self.keep_task.cancel()

        self.keep_task = asyncio.create_task(self.keep_listen_key(listen_key))
        return f"{self.base_url}{listen_key}"

    async def keep_listen_key(self, listen_key: str) -> None:
        try:
            while True:
                await asyncio.sleep(30 * 60)
                await self.rest.keep_listen_key_async(listen_key)
        except asyncio.CancelledError:
            pass
        except RestResponseError as e:
            return self.rest.log(f"Failed to keep listen key: {e}", "ERROR")

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    def decode_user_event(self, raw_data: bytes | memoryview) -> bytes | None:
        data: dict[str, Any] = self.decoder.decode(raw_data)
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
