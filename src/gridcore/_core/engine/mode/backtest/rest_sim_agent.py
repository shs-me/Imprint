from ....configurations import cfgBacktesting


class RestSimAgent:
    def __init__(self, symbol: str, cfgBT: cfgBacktesting) -> None:
        self.symbol: str = symbol

        self.cfgBT: cfgBacktesting = cfgBT
        self.tick_size: str = self.cfgBT.tick_size
        self.lot_size: str = self.cfgBT.lot_size
        self.min_order_size: float = self.cfgBT.min_order_size
        self.maker_commission: float = self.cfgBT.maker_commission
        self.taker_commission: float = self.cfgBT.taker_commission
        self.balance: float = self.cfgBT.balance
        self.orderId: int = 0

    def get_tick_size(self) -> str:
        return self.tick_size

    def get_lot_size(self) -> str:
        return self.lot_size

    def get_min_order_size_usdt(self) -> float:
        return self.min_order_size

    def get_balance(self, free: bool = True) -> float:
        return self.balance if free else self.balance

    def get_commission(self, is_maker: bool = True) -> float:
        return self.maker_commission if is_maker else self.taker_commission
