from typing import override

from msgspec import Struct
from msgspec.json import Encoder

from imprint.api.base import OrderEncoder


class NewOrderParam(Struct):
    category: str
    symbol: str
    side: str
    positionIdx: int
    orderType: str
    qty: str
    orderLinkId: str
    timeInForce: str
    price: str | None = None


class CancelOrderParam(Struct):
    category: str
    symbol: str
    orderLinkId: str


class Order(Struct):
    req_id: str
    op: str
    args: list[NewOrderParam] | list[CancelOrderParam]


class BybitOrderEncoder(OrderEncoder):
    encoder: Encoder

    def __post_init__(self) -> None:
        self.encoder = Encoder()

    @override
    def encode_new_order(
        self,
        timestamp: int,
        client_order_id: int,
        symbol: str,
        is_buy: bool,
        is_long: bool,
        is_market: bool,
        price: float,
        qty: float,
        time_in_force: str = "GTC",
    ) -> bytes:
        payload = Order(
            req_id=str(client_order_id),
            op="order.create",
            args=[
                NewOrderParam(
                    category="linear",
                    symbol=symbol,
                    side="Buy" if is_buy else "Sell",
                    positionIdx=1 if is_long else 2,
                    orderType="Market" if is_market else "Limit",
                    qty=str(qty),
                    orderLinkId=f"gc_{client_order_id}",
                    timeInForce=time_in_force,
                    price=None if is_market else str(price),
                )
            ],
        )
        return self.encoder.encode(payload)

    @override
    def encode_cancel_order(self, symbol: str, client_order_id: int) -> bytes:
        payload = Order(
            req_id=str(client_order_id),
            op="order.cancel",
            args=[
                CancelOrderParam(
                    category="linear",
                    symbol=symbol,
                    orderLinkId=f"gc_{client_order_id}",
                )
            ],
        )
        return self.encoder.encode(payload)
