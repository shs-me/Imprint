"""Exchange REST API client interface stub."""


class RestAgent:
    """REST client providing symbol metadata, account balances, and order management methods."""

    def __init__(self, symbol: str) -> None:
        self.symbol: str = symbol

    def get_tick_size(self) -> str:
        """Fetches minimum tick size increment for target symbol."""

        return "0.01"

    def get_lot_size(self) -> str:
        """Fetches minimum lot size increment for target symbol."""

        return "0.001"

    def get_min_order_size_usdt(self) -> float:
        """Fetches minimum required order nominal size in USDT."""

        return 5

    def get_balance(self, free: bool = True) -> float:
        """Fetches available account equity balance."""

        return 1000

    def get_commission(self, is_maker: bool = True) -> float:
        """Fetches maker or taker commission rate for account."""

        return 0.002 if is_maker else 0.005

    def send_new_order(self) -> None:
        return

    def cancel_new_order(self) -> None:
        return
