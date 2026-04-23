import time

from core.utils.monitoring.agent_manager import AgentManager


class RestSimAgent:
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager

        self.symbol = manager.symbol
        self.cfgBT = manager.cfgBacktesting
        self.tick_size = self.cfgBT.tick_size
        self.lot_size = self.cfgBT.lot_size

        self.orderId = 0
        self.makerCommission = self.cfgBT.maker_commission
        self.takerCommission = self.cfgBT.taker_commision
        self.balance = self.cfgBT.balance

    def ping(self) -> bool:
        return True

    def get_server_time(self) -> int:
        return round(time.time() * 1000)

    def get_tick_size(self) -> str:
        return self.tick_size

    def get_lot_size(self) -> str:
        return self.lot_size

    def get_commission(self, maker: bool = True) -> float:
        return self.makerCommission if maker else self.takerCommission

    def get_balance(self, free: bool = True) -> float:
        return self.balance if free else self.balance

    def send_new_order(self) -> None | tuple[int, int]:
        self.orderId += 1
        return self.orderId, round(time.time() * 1000)

    def cancel_open_order(self, orderId: int) -> None | tuple[int, int]:
        self.orderId += 1
        return self.orderId, round(time.time() * 1000)

    def check_status_order(self, orderId: int) -> bool:
        return True
