from dataclasses import dataclass
from typing import Any, override

from websockets import ClientConnection

from imprint.configs import OrderEncoder


@dataclass(slots=True)
class BybitOrderEncoder(OrderEncoder[Any]):
    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    def encode_new_order(
        self,
        timestamp: int,
        client_order_id: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        price: float,
        qty: float,
        time_in_force: str = "GTC",
    ) -> bytes: ...

    @override
    def encode_cancel_order(self, client_order_id: int) -> bytes: ...

    @override
    def encode_market_trigger_order(
        self,
        timestamp: int,
        client_order_id: int,
        is_long: bool,
        is_buy: bool,
        price: float,
        qty: float,
        time_in_force: str = "GTC",
    ) -> bytes: ...
