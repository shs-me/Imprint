import asyncio
from asyncio import Task
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, override

from websockets import ClientConnection

from imprint._core.utils.base_rest import RestResponseError
from imprint.configs import BalanceData, OrderData, UserStreamDecoder


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
    def decode(
        self, raw_data: bytes | memoryview
    ) -> Iterator[OrderData | BalanceData]:
        data: dict[str, Any] = self.decoder.decode(raw_data)
        event_type = data.get("e")

        if event_type == "ORDER_TRADE_UPDATE":
            self.order_data.timestamp = 0
            self.order_data.order_param = 0
            self.order_data.order_id = 0
            self.order_data.client_order_id = 0
            self.order_data.nPrice = 0
            self.order_data.nQty = 0
            self.order_data.nCommission = 0
            yield self.order_data

        elif event_type == "ACCOUNT_UPDATE":
            self.balance_data.nBalance = 0
            self.balance_data.lockedNbalance = 0
            self.balance_data.availableNbalance = 0
            yield self.balance_data
