import asyncio
from asyncio import Task
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import override

from msgspec import Struct
from websockets import ClientConnection

from example.binance.rest_adapter import BinanceFuturesREST
from imprint._core import constant as c
from imprint._core.utils.base_adapters import (
    BalanceData,
    OrderData,
    UserStreamDecoder,
)
from imprint._core.utils.base_rest import RestResponseError


class OrderUpdateData(Struct):
    s: str  # Symbol
    c: str  # Client Order ID
    S: str  # Side (BUY/SELL)
    o: str  # Order Type (LIMIT/MARKET/etc)
    X: str  # Execution Status (NEW/FILLED/CANCELED/PARTIALLY_FILLED/etc)
    i: int  # Order ID
    p: str  # Original Price
    q: str  # Original Quantity
    n: str  # Commission
    ps: str  # Position Side (LONG/SHORT/BOTH)
    T: int  # Order Trade Time / Transaction Time


class OrderUpdateEvent(Struct, tag="ORDER_TRADE_UPDATE", tag_field="e"):
    o: OrderUpdateData
    E: int  # Event Time


class BalanceItem(Struct):
    a: str  # Asset name
    wb: str  # Wallet Balance
    cw: str  # Cross Wallet Balance
    bc: str  # Balance Change


class AccountUpdateData(Struct):
    B: list[BalanceItem]


class AccountUpdateEvent(Struct, tag="ACCOUNT_UPDATE", tag_field="e"):
    a: AccountUpdateData
    E: int  # Event Time


class UnknownEvent(Struct, tag=None, tag_field="e"): ...


BinanceUserStreamEvent = OrderUpdateEvent | AccountUpdateEvent | UnknownEvent


@dataclass(slots=True)
class BinanceUserStreamDecoder(
    UserStreamDecoder[BinanceFuturesREST, BinanceUserStreamEvent]
):
    asset: str = "USDT"
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
        event: BinanceUserStreamEvent = self.decoder.decode(raw_data)

        if isinstance(event, OrderUpdateEvent):
            data: OrderUpdateData = event.o
            order_param: int = 0

            if data.ps == "LONG":
                order_param |= c.OF_LONG
            elif data.ps == "SHORT":
                order_param |= c.OF_SHORT

            if data.S == "BUY":
                order_param |= c.OF_BUY
            elif data.S == "SELL":
                order_param |= c.OF_SELL

            if data.o == "LIMIT":
                order_param |= c.OF_LIMIT
            elif data.o == "MARKET":
                order_param |= c.OF_MARKET

            if data.X == "NEW":
                order_param |= c.OF_NEW
            elif data.X in ("FILLED", "PARTIALLY_FILLED"):
                order_param |= c.OF_FILLED
            elif data.X in ("CANCELED", "EXPIRED", "REJECTED"):
                order_param |= c.OF_CANCELED

            client_order_id = int(data.c.split("_")[1])

            self.order_data.timestamp = data.T or event.E
            self.order_data.order_param = order_param
            self.order_data.order_id = data.i
            self.order_data.client_order_id = client_order_id
            self.order_data.nPrice = int(float(data.p) * self.price_mult)
            self.order_data.nQty = int(float(data.q) * self.qty_mult)
            self.order_data.nCommission = int(float(data.n) * self.scale_mult)
            yield self.order_data

        elif isinstance(event, AccountUpdateEvent):
            for b in event.a.B:
                if b.a == self.asset:
                    wallet_balance = float(b.wb)
                    cross_wallet = float(b.cw)
                    n_balance = int(wallet_balance * self.scale_mult)
                    avail_balance = int(cross_wallet * self.scale_mult)
                    locked_balance = max(0, n_balance - avail_balance)

                    self.balance_data.nBalance = n_balance
                    self.balance_data.lockedNbalance = locked_balance
                    self.balance_data.availableNbalance = avail_balance
                    yield self.balance_data
                    break
