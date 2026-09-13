import asyncio
import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Semaphore
from typing import Any, override

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

    encoder: OrderEncoder[Any] = field(init=False)
    loop: asyncio.AbstractEventLoop = field(init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.price_mult = self.manager.cfgCoin.price_mult
        self.price_prec = self.manager.cfgCoin.price_prec
        self.qty_mult = self.manager.cfgCoin.qty_mult
        self.qty_prec = self.manager.cfgCoin.qty_prec

        m_name: str = self.manager.cfgSetup.order_encoder_module
        c_name: str = self.manager.cfgSetup.order_encoder_class_name
        encoder_type: type[OrderEncoder[Any]] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_log(
            f"{encoder_type.__name__} used as {OrderEncoder.__name__}"
        )
        self.encoder = encoder_type(symbol=self.symbol, rest=self.rest)

        self.loop = asyncio.get_event_loop()

    @override
    async def on_pre_connect(self) -> None: ...

    @override
    async def on_connection(self, ws: ClientConnection) -> None:
        await self.encoder.on_connection(ws)

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        _ = self.os.ring_buf
        # - - -
        await self.loop.run_in_executor(None, self.wss_sem.acquire)
        if _.wid_buf[0] != _.rid_buf[0]:
            payload: bytes = self.to_payload()
            await ws.send(payload, text=True)

    def to_payload(self) -> bytes:
        timestamp, order_param, client_order_id, nPrice, nQty = (
            self.os.ring_buf.get_data()
        )

        is_long: bool = bool(order_param & c.OF_LONG)
        is_buy: bool = bool(order_param & c.OF_BUY)

        price: float = round(nPrice / self.price_mult, self.price_prec)
        qty: float = round(nQty / self.qty_mult, self.qty_prec)

        if order_param & c.OF_CANCEL:
            return self.encoder.encode_cancel_order(
                client_order_id=client_order_id
            )
        else:
            if (order_param & c.OF_MARKET) or (order_param & c.OF_LIMIT):
                return self.encoder.encode_new_order(
                    timestamp=timestamp,
                    client_order_id=client_order_id,
                    is_long=is_long,
                    is_buy=is_buy,
                    is_market=bool(order_param & c.OF_MARKET),
                    price=price,
                    qty=qty,
                )
            else:
                return self.encoder.encode_market_trigger_order(
                    timestamp=timestamp,
                    client_order_id=client_order_id,
                    is_long=is_long,
                    is_buy=is_buy,
                    price=price,
                    qty=qty,
                )
