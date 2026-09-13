from dataclasses import dataclass
from typing import override

from msgspec import Struct
from websockets import ClientConnection

from example.binance.rest_adapter import BinanceFuturesREST
from imprint.configs import OrderEncoder


class NewOrderParam(Struct):
    symbol: str
    side: str
    positionSide: str
    type: str
    quantity: str
    newClientOrderId: str
    timestamp: int
    price: str | None = None
    stopPrice: str | None = None
    timeInForce: str | None = None


class CancelOrderParam(Struct):
    symbol: str
    origClientOrderId: str


class Order(Struct):
    id: int
    method: str
    params: NewOrderParam | CancelOrderParam


class LoginParam(Struct):
    apiKey: str
    signature: str
    timestamp: int


class LoginRequest(Struct):
    id: str
    method: str
    params: LoginParam


@dataclass(slots=True)
class BinanceOrderEncoder(OrderEncoder[BinanceFuturesREST]):
    @override
    async def on_connection(self, ws: ClientConnection) -> None:
        timestamp = self.rest._get_timestamp_ms()
        api_key = self.rest.api_key

        payload_to_sign = f"apiKey={api_key}&timestamp={timestamp}"
        signature = self.rest._sign_hmac_sha256(payload_to_sign)

        login_payload = LoginRequest(
            id="auth_session",
            method="session.logon",
            params=LoginParam(
                apiKey=api_key, signature=signature, timestamp=timestamp
            ),
        )

        self.rest.log(
            "Sending session.logon for order connection authorization..."
        )
        await ws.send(self.encoder.encode(login_payload))

        response_raw = await ws.recv()
        self.rest.log(f"Auth response received: {response_raw!r}")

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
    ) -> bytes:
        payload = Order(
            id=client_order_id,
            method="order.place",
            params=NewOrderParam(
                symbol=self.symbol,
                side="BUY" if is_buy else "SELL",
                positionSide="LONG" if is_long else "SHORT",
                type="MARKET" if is_market else "LIMIT",
                quantity=f"{qty}",
                newClientOrderId=f"im_{client_order_id}",
                timestamp=timestamp,
                price=None if is_market else str(price),
                timeInForce=None if is_market else time_in_force,
            ),
        )
        return self.encoder.encode(payload)

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
    ) -> bytes:
        payload = Order(
            id=client_order_id,
            method="order.place",
            params=NewOrderParam(
                symbol=self.symbol,
                side="BUY" if is_buy else "SELL",
                positionSide="LONG" if is_long else "SHORT",
                type="STOP_MARKET",
                quantity=f"{qty}",
                newClientOrderId=f"im_{client_order_id}",
                timestamp=timestamp,
                stopPrice=str(price),
                timeInForce=time_in_force,
            ),
        )
        return self.encoder.encode(payload)

    @override
    def encode_cancel_order(self, client_order_id: int) -> bytes:
        payload = Order(
            id=client_order_id,
            method="order.cancel",
            params=CancelOrderParam(
                symbol=self.symbol,
                origClientOrderId=f"im_{client_order_id}",
            ),
        )
        return self.encoder.encode(payload)
