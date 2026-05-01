import time

from core.configurations import ConfigurationBacktesting


class RestAgent:
    def __init__(
        self, symbol: str, backtesting: bool, cfgBacktesting: ConfigurationBacktesting
    ) -> None:
        self.symbol: str = symbol
        self.backtesting: bool = backtesting
        # Backtesting
        self.cfgBT: ConfigurationBacktesting = cfgBacktesting
        self.tick_size: str = self.cfgBT.tick_size
        self.lot_size: str = self.cfgBT.lot_size
        self.minOrderSizeUsdt: float = self.cfgBT.minOrderSizeUSDT
        self.makerCommission: float = self.cfgBT.maker_commission
        self.takerCommission: float = self.cfgBT.taker_commision
        self.balance: float = self.cfgBT.balance
        self.orderId: int = 0

    # Symbol data
    def get_tick_size(self) -> str:
        if self.backtesting:
            return self.tick_size
        else:
            return self.tick_size

    def get_lot_size(self) -> str:
        if self.backtesting:
            return self.lot_size
        else:
            return self.lot_size

    def get_min_order_size_usdt(self) -> float:
        return self.minOrderSizeUsdt

    # User Data
    def get_balance(self, free: bool = True) -> float:
        if self.backtesting:
            return self.balance if free else self.balance
        else:
            return self.balance if free else self.balance

    def get_commission(self, is_maker: bool = True) -> float:
        if self.backtesting:
            return self.makerCommission if is_maker else self.takerCommission
        else:
            return self.makerCommission if is_maker else self.takerCommission

    def send_new_order(
        self,
        price: float,
        qty: float,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
    ) -> tuple:
        if self.backtesting:
            self.orderId += 1
            return self.orderId, round(time.time() * 1000)

        else:
            self.orderId += 1
            return self.orderId, round(time.time() * 1000)

    def cancel_new_order(self, orderId: int) -> tuple:
        if self.backtesting:
            return orderId, round(time.time() * 1000)
        else:
            return orderId, round(time.time() * 1000)
