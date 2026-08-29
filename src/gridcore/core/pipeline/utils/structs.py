from __future__ import annotations

from typing import TYPE_CHECKING

from msgspec import Struct, field

if TYPE_CHECKING:
    from ...configs import AggTradesStructFieldsNames, OrderStructFieldsNames


def create_aggtrades_struct(fields_names: AggTradesStructFieldsNames):
    class AggTrades(Struct):
        price: float = field(name=fields_names.price)
        qty: float = field(name=fields_names.qty)
        timestamp: int = field(name=fields_names.timestamp)
        is_sell: bool = field(name=fields_names.is_sell)

    return AggTrades


def create_order_struct(order_fields_names: OrderStructFieldsNames):
    class Param(Struct):
        symbol: str = field(name=order_fields_names.symbol)
        side: str = field(name=order_fields_names.side)
        type: str = field(name=order_fields_names.type)
        timeInForce: str = field(name=order_fields_names.timeInForce)
        timestamp: int = field(name=order_fields_names.timestamp)
        quantity: float = field(name=order_fields_names.quantity)
        price: float | None = field(default=None, name=order_fields_names.price)

    class Order(Struct):
        order_id: int = field(name=order_fields_names.order_id)
        type_place: str = field(name=order_fields_names.type_place)
        param: Param

    return Param, Order
