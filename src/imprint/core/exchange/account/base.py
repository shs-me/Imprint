from dataclasses import dataclass, field
from typing import final

from imprint.core import constant as c
from imprint.core.exchange.account.converter import to_nMargin
from imprint.core.ipc import NodeManager


@dataclass(slots=True)
class Base:
    manager: NodeManager

    price_prec: int = field(init=False)
    qty_prec: int = field(init=False)
    price_mult: int = field(init=False)
    qty_mult: int = field(init=False)

    scale_prec: int = field(init=False)
    scale_mult: int = field(init=False)
    leverage: int = field(init=False)
    takerNcommission: int = field(init=False)
    makerNcommission: int = field(init=False)
    start_balance: float = field(init=False)
    startNbalance: int = field(init=False)

    nBalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    lockedNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    availableNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    dynamicNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    def __post_init__(self) -> None:
        cfgCoin = self.manager.cfgCoin
        self.price_prec = cfgCoin.price_prec
        self.qty_prec = cfgCoin.qty_prec
        self.price_mult = cfgCoin.price_mult
        self.qty_mult = cfgCoin.qty_mult

        cfgAC = self.manager.cfgAccount
        self.scale_prec = cfgAC.scale_prec
        self.scale_mult = cfgAC.scale_mult
        self.leverage = cfgAC.leverage
        self.takerNcommission = cfgAC.taker_commission.int_
        self.makerNcommission = cfgAC.maker_commission.int_
        self.start_balance = cfgAC.balance

        self.startNbalance = round(cfgAC.balance * self.scale_mult)

        self.nBalance[0] = self.startNbalance
        self.availableNbalance[0] = self.startNbalance
        self.dynamicNbalance[0] = self.startNbalance

    @final
    def update_local_lockedNbalance(
        self, nPrice: int, nQty: int, order_param: int
    ) -> None:
        is_long = bool(order_param & c.OF_LONG)
        is_buy = bool(order_param & c.OF_BUY)
        if (is_buy and is_long) or (not is_long and not is_buy):
            if bool(order_param & c.OF_LIMIT):
                self.lockedNbalance[0] += to_nMargin(
                    nPrice,
                    nQty,
                    self.leverage,
                    self.price_mult,
                    self.qty_mult,
                    self.scale_mult,
                )

        self.post_update_lockedNbalance()

    def post_update_lockedNbalance(self) -> None: ...
