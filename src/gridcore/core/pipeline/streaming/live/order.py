import asyncio
import importlib
import struct
from dataclasses import dataclass, field
from multiprocessing.synchronize import Semaphore
from typing import override

from websockets import ClientConnection

from .... import constant as c
from ....ipc import NodeManager
from ...utils.base_adapters import OrderEncoder
from .base import Base


@dataclass(slots=True, init=False)
class Order(Base):
    wss_sem: Semaphore

    price_mult: int = field(init=False)
    price_prec: int = field(init=False)
    qty_prec: int = field(init=False)
    qty_mult: int = field(init=False)

    order_encoder: OrderEncoder = field(init=False)
    uri: str = field(init=False)
    loop: asyncio.AbstractEventLoop = field(init=False)

    def __init__(self, manager: NodeManager, wss_sem: Semaphore) -> None:
        self.wss_sem = wss_sem

        self.price_mult = manager.cfgCoin.price_mult
        self.price_prec = manager.cfgCoin.price_prec
        self.qty_prec = manager.cfgCoin.qty_mult
        self.qty_mult = manager.cfgCoin.qty_prec

        m_name: str = manager.cfgSetup.order_encoder_module
        c_name: str = manager.cfgSetup.order_encoder_class_name
        encoder_type: type[OrderEncoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.order_encoder = encoder_type()

        self.uri = manager.cfgConnector.set_user_data_uri_for_wss

        super().__init__(manager, self.uri)

        self.loop = asyncio.get_event_loop()

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        await self.loop.run_in_executor(None, self.wss_sem.acquire)

        if self.sus_wid[0] != self.sus_rid[0]:
            payload: bytes = self.get_order_payload()
            await ws.send(payload, text=True)

    def get_order_payload(self) -> bytes:
        cell: int = self.sus_rid[0]
        lrd: int = self.sus_data_header[cell]
        start: int = cell * self.sus_data_size

        raw_data: bytes = self.to_payload(self.sus_data[start : start + lrd])

        new_cell: int = cell + 1
        self.sus_rid[0] = new_cell if new_cell < self.sus_cell_amount else 0

        return raw_data

    def to_payload(self, raw_data: memoryview) -> bytes:
        timestamp, order_param, client_order_id, nPrice, nQty = struct.unpack(
            "@qqqqq", raw_data
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
