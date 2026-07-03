from ....configurations import ConfigurationBacktesting


class RestSimAgent:
    def __init__(self, symbol: str, cfgBacktesting: ConfigurationBacktesting) -> None:
        self.symbol: str = symbol

        self.cfgBT = cfgBacktesting
        self.tick_size: str = self.cfgBT.tick_size
        self.lot_size: str = self.cfgBT.lot_size
        self.minOrderSizeUsdt: float = self.cfgBT.minOrderSizeUSDT
        self.makerCommission: float = self.cfgBT.maker_commission
        self.takerCommission: float = self.cfgBT.taker_commision
        self.balance: float = self.cfgBT.balance
        self.orderId: int = 0

    def get_tick_size(self) -> str:
        return self.tick_size

    def get_lot_size(self) -> str:
        return self.lot_size

    def get_min_order_size_usdt(self) -> float:
        return self.minOrderSizeUsdt

    def get_balance(self, free: bool = True) -> float:
        return self.balance if free else self.balance

    def get_commission(self, is_maker: bool = True) -> float:
        return self.makerCommission if is_maker else self.takerCommission
