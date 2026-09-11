import asyncio
import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Semaphore
from typing import override

from websockets import ClientConnection

from imprint._core import constant as c
from imprint._core.pipeline.streaming.live.base import Base
from imprint._core.utils import OrderEncoder


@dataclass(slots=True)
class Order(Base):
    wss_sem: Semaphore

    price_mult: int = field(init=False)
    price_prec: int = field(init=False)
    qty_prec: int = field(init=False)
    qty_mult: int = field(init=False)

    order_encoder: OrderEncoder = field(init=False)
    loop: asyncio.AbstractEventLoop = field(init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.price_mult = self.manager.cfgCoin.price_mult
        self.price_prec = self.manager.cfgCoin.price_prec
        self.qty_mult = self.manager.cfgCoin.qty_mult
        self.qty_prec = self.manager.cfgCoin.qty_prec

        m_name: str = self.manager.cfgSetup.order_encoder_module
        c_name: str = self.manager.cfgSetup.order_encoder_class_name
        encoder_type: type[OrderEncoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_log(
            f"{encoder_type.__name__} used as {OrderEncoder.__name__}"
        )
        self.order_encoder = encoder_type(self.rest)

        self.loop = asyncio.get_event_loop()

    @override
    async def on_pre_connect(self) -> None: ...

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        _ = self.os.ring_buf
        await self.loop.run_in_executor(None, self.wss_sem.acquire)

        if _.wid_buf[0] != _.rid_buf[0]:
            payload: bytes | None = self.to_payload()
            await ws.send(payload, text=True)

    def to_payload(self) -> bytes:
        timestamp, order_param, client_order_id, nPrice, nQty = (
            self.os.ring_buf.get_data()
        )

        price: float = round(nPrice / self.price_mult, self.price_prec)
        qty: float = round(nQty / self.qty_mult, self.qty_prec)

        is_buy: bool = bool(order_param & c.OF_BUY)
        is_long: bool = bool(order_param & c.OF_LONG)
        is_market: bool = bool(order_param & c.OF_MARKET)

        if bool(order_param & c.OF_CANCELED):
            return self.order_encoder.encode_cancel_order(
                symbol=self.symbol, client_order_id=client_order_id
            )
        else:
            return self.order_encoder.encode_new_order(
                timestamp=timestamp,
                client_order_id=client_order_id,
                symbol=self.symbol,
                is_buy=is_buy,
                is_long=is_long,
                is_market=is_market,
                price=price,
                qty=qty,
            )
