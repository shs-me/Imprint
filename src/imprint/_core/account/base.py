"""Base configuration binding for account balance and scaling properties."""

from dataclasses import dataclass, field

from imprint._core.ipc import NodeManager


@dataclass(slots=True)
class Base:
    """Bind account balance settings, pricing/quantity scale factors, and memory buffers.

    Attributes
    ----------
    price_prec : int
        Decimal precision for asset prices.
    qty_prec : int
        Decimal precision for asset quantities.
    price_mult : int
        Multiplier for scaling floating-point prices to integer fixed-point units.
    qty_mult : int
        Multiplier for scaling floating-point quantities to integer fixed-point units.
    scale_prec : int
        Decimal precision for account balances.
    scale_mult : int
        Multiplier for scaling floating-point account balances to integer fixed-point units.
    leverage : int
        Account leverage multiplier applied to order margins.
    start_balance : float
        Initial account balance in floating-point currency units.
    startNbalance : int
        Initial account balance in scaled integer fixed-point units.
    nBalance : memoryview
        Shared memory buffer view holding current account balance as int64.
    lockedNbalance : memoryview
        Shared memory buffer view holding current locked margin balance as int64.
    availableNbalance : memoryview
        Shared memory buffer view holding current available balance as int64.
    dynamicNbalance : memoryview
        Shared memory buffer view holding current equity/dynamic balance as int64.
    """

    manager: NodeManager

    price_prec: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    qty_prec: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    price_mult: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    qty_mult: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    scale_prec: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    scale_mult: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    leverage: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    startNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    start_balance: float = field(init=False)

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
        self.init()

    def init(self) -> None:
        cfgCoin = self.manager.cfgCoin
        self.price_prec[0] = cfgCoin.price_prec
        self.qty_prec[0] = cfgCoin.qty_prec
        self.price_mult[0] = cfgCoin.price_mult
        self.qty_mult[0] = cfgCoin.qty_mult

        cfgAC = self.manager.cfgAccount
        self.scale_prec[0] = cfgAC.scale_prec
        self.scale_mult[0] = cfgAC.scale_mult
        self.leverage[0] = cfgAC.leverage
        self.start_balance = cfgAC.balance

        self.startNbalance[0] = round(cfgAC.balance * self.scale_mult[0])

        self.nBalance[0] = self.startNbalance[0]
        self.availableNbalance[0] = self.startNbalance[0]
        self.dynamicNbalance[0] = self.startNbalance[0]

    def reset(self) -> None:
        self.init()

        self.lockedNbalance[0] = 0
