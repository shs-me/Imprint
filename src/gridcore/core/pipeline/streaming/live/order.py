import asyncio
import struct
from multiprocessing.synchronize import Semaphore
from typing import override

from msgspec.json import Encoder
from websockets import ClientConnection

from .... import constant as c
from ....ipc import NodeManager
from ...utils.structs import create_order_struct
from .base import Base


class Order(Base):
    def __init__(self, manager: NodeManager, wss_sem: Semaphore) -> None:
        self.wss_sem: Semaphore = wss_sem

        self.price_mult: int = manager.cfgCoin.price_mult
        self.price_prec: int = manager.cfgCoin.price_prec
        self.qty_prec: int = manager.cfgCoin.qty_mult
        self.qty_mult: int = manager.cfgCoin.qty_prec

        fields_names = manager.cfgSetup.order_encoder_struct_fields_names
        self.order_param_type, self.order_type = create_order_struct(fields_names)
        self.encoder: Encoder = Encoder()

        self.send_order_uri: str = manager.cfgConnector.set_user_data_uri_for_wss

        super().__init__(manager, self.send_order_uri)

        self.loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        await self.loop.run_in_executor(None, self.wss_sem.acquire)

        if self.sus_wid[0] != self.sus_rid[0]:
            if raw_data := self.get_raw_data(
                reader_id=self.sus_rid,
                data=self.sus_data,
                data_header=self.sus_data_header,
                data_size=self.sus_data_size,
                cell_amount=self.sus_cell_amount,
            ):
                await ws.send(raw_data, text=True)

    def get_raw_data(
        self,
        reader_id: memoryview,
        data: memoryview,
        data_header: memoryview,
        data_size: int,
        cell_amount: int,
    ) -> bytes:
        cell: int = reader_id[0]
        lrd: int = data_header[cell]
        start: int = cell * data_size

        raw_data: bytes = self.to_payload(data[start : start + lrd])

        new_cell: int = cell + 1
        reader_id[0] = new_cell if new_cell < cell_amount else 0

        return raw_data

    def to_payload(self, raw_data: memoryview) -> bytes:
        timestamp, order_param, client_order_id, nPrice, nQty = struct.unpack(
            "@qqqqq", raw_data
        )

        price: float = round(nPrice / self.price_mult, self.price_prec)
        qty: float = round(nQty / self.qty_mult, self.qty_prec)

        side: str = "LONG" if bool(order_param & c.OF_LONG) else "SHORT"
        type: str = "BUY" if bool(order_param & c.OF_BUY) else "SELL"

        return self.encoder.encode(
            self.order_type(
                order_id=client_order_id,
                type_place="",
                param=self.order_param_type(
                    symbol=self.symbol,
                    side=side,
                    type=type,
                    timeInForce="GTC",
                    quantity=qty,
                    price=price,
                    timestamp=timestamp,
                ),
            )
        )
