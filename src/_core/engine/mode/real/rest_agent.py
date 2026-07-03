class RestAgent:
    def __init__(self, symbol: str) -> None:
        self.symbol: str = symbol

    def get_tick_size(self) -> str:
        return "0.01"

    def get_lot_size(self) -> str:
        return "0.001"

    def get_min_order_size_usdt(self) -> float:
        return 5

    def get_balance(self, free: bool = True) -> float:
        return 1000

    def get_commission(self, is_maker: bool = True) -> float:
        return 0.002 if is_maker else 0.005

    def send_new_order(self) -> None:
        return

    def cancel_new_order(self) -> None:
        return
