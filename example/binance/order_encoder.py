from typing import override

from msgspec import Struct
from msgspec.json import Encoder

from imprint.api.setup import OrderEncoder


class NewOrderParam(Struct):
    symbol: str
    side: str
    positionSide: str
    type: str
    quantity: str
    newClientOrderId: str
    timestamp: int
    price: str | None = None
    timeInForce: str | None = None


class CancelOrderParam(Struct):
    symbol: str
    origClientOrderId: str


class Order(Struct):
    id: int
    method: str
    params: NewOrderParam | CancelOrderParam


class BinanceOrderEncoder(OrderEncoder):
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
            id=client_order_id,
            method="order.place",
            params=NewOrderParam(
                symbol=symbol,
                side="BUY" if is_buy else "SELL",
                positionSide="LONG" if is_long else "SHORT",
                type="MARKET" if is_market else "LIMIT",
                quantity=f"{qty:.6f}".rstrip("0").rstrip("."),
                newClientOrderId=f"gc_{client_order_id}",
                timestamp=timestamp,
                price=None if is_market else str(price),
                timeInForce=None if is_market else time_in_force,
            ),
        )
        return self.encoder.encode(payload)

    @override
    def encode_cancel_order(self, symbol: str, client_order_id: int) -> bytes:
        payload = Order(
            id=client_order_id,
            method="order.cancel",
            params=CancelOrderParam(
                symbol=symbol,
                origClientOrderId=f"gc_{client_order_id}",
            ),
        )
        return self.encoder.encode(payload)
