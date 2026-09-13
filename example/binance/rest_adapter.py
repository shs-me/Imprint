from dataclasses import dataclass
from typing import Any, override

from msgspec import Struct

from imprint.configs import ExchangeREST


class BaseFilter(Struct, tag_field="filterType"): ...


class PriceFilter(BaseFilter, tag="PRICE_FILTER"):
    minPrice: str
    maxPrice: str
    tickSize: str


class LotSizeFilter(BaseFilter, tag="LOT_SIZE"):
    minQty: str
    maxQty: str
    stepSize: str


class MinNotionalFilter(BaseFilter, tag="MIN_NOTIONAL"):
    notional: str


class MarketLotSizeFilter(BaseFilter, tag="MARKET_LOT_SIZE"): ...


class PercentPriceFilter(BaseFilter, tag="PERCENT_PRICE"): ...


class MaxNumOrdersFilter(BaseFilter, tag="MAX_NUM_ORDERS"): ...


class MaxNumAlgoOrdersFilter(BaseFilter, tag="MAX_NUM_ALGO_ORDERS"): ...


class PositionRiskControl(BaseFilter, tag="POSITION_RISK_CONTROL"): ...


class UnknownFilter(BaseFilter, tag=None): ...


class SymbolInfo(Struct):
    symbol: str
    filters: list[
        PriceFilter
        | LotSizeFilter
        | MarketLotSizeFilter
        | MinNotionalFilter
        | PercentPriceFilter
        | MaxNumOrdersFilter
        | MaxNumAlgoOrdersFilter
        | PositionRiskControl
        | UnknownFilter
    ]


class ExchangeInfoResponse(Struct):
    symbols: list[SymbolInfo]


class FutureBalance(Struct):
    asset: str
    balance: str
    availableBalance: str


class ListenKeyResponse(Struct, rename="camel"):
    listen_key: str


class PositionRiskItem(Struct, rename="camel"):
    symbol: str
    position_amt: float
    entry_price: float


@dataclass(slots=True)
class BinanceFuturesREST(ExchangeREST):
    def _auth_headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def _signed_params(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        p: dict[str, Any] = params.copy() if params else {}
        p["timestamp"] = self._get_timestamp_ms()
        p["recvWindow"] = self.recv_window

        query_str: str = "&".join(f"{k}={v}" for k, v in p.items())
        p["signature"] = self._sign_hmac_sha256(query_str)
        return p

    @override
    def _fetch_symbol_data(self) -> tuple[str, str, float]:
        res: ExchangeInfoResponse = self.send_sync(
            "GET", "/fapi/v1/exchangeInfo", response_type=ExchangeInfoResponse
        )
        tick_size, lot_size, min_order_size = "", "", 0.0
        for symbol_info in res.symbols:
            if symbol_info.symbol == self.symbol:
                for f in symbol_info.filters:
                    if isinstance(f, PriceFilter):
                        tick_size = f.tickSize
                    elif isinstance(f, LotSizeFilter):
                        lot_size = f.stepSize
                    elif isinstance(f, MinNotionalFilter):
                        min_order_size = float(f.notional)

        return tick_size, lot_size, min_order_size

    @override
    def get_balance(self, asset: str = "USDT") -> float:
        params: dict[str, Any] = self._signed_params()
        balances: list[FutureBalance] = self.send_sync(
            "GET",
            "/fapi/v2/balance",
            params=params,
            headers=self._auth_headers(),
            response_type=list[FutureBalance],
        )
        for item in balances:
            if item.asset == asset:
                return float(item.balance)

        return 0.0

    @override
    def set_leverage(self, leverage: int) -> None:
        params: dict[str, Any] = self._signed_params(
            {"symbol": self.symbol, "leverage": leverage}
        )
        self.send_sync(
            "POST",
            "/fapi/v1/leverage",
            params=params,
            headers=self._auth_headers(),
        )

    async def get_listen_key_async(self) -> str:
        res: ListenKeyResponse = await self.send_async(
            "POST",
            "/fapi/v1/listenKey",
            headers=self._auth_headers(),
            response_type=ListenKeyResponse,
        )
        return res.listen_key

    async def keep_listen_key_async(self, listen_key: str) -> bool:
        params: dict[str, Any] = self._signed_params({"listenKey": listen_key})
        await self.send_async(
            "PUT",
            "/fapi/v1/listenKey",
            params=params,
            headers=self._auth_headers(),
        )
        return True

    async def close_listen_key_async(self, listen_key: str) -> bool:
        params: dict[str, Any] = self._signed_params({"listenKey": listen_key})
        await self.send_async(
            "DELETE",
            "/fapi/v1/listenKey",
            params=params,
            headers=self._auth_headers(),
        )
        return True

    @override
    def cancel_all_orders(self) -> bool:
        params: dict[str, Any] = self._signed_params({"symbol": self.symbol})
        self.send_sync(
            "DELETE",
            "/fapi/v1/allOpenOrders",
            params=params,
            headers=self._auth_headers(),
        )
        return True

    @override
    def close_all_positions(self) -> bool:
        params: dict[str, Any] = self._signed_params({"symbol": self.symbol})
        positions: list[PositionRiskItem] = self.send_sync(
            "GET",
            "/fapi/v2/positionRisk",
            params=params,
            headers=self._auth_headers(),
            response_type=list[PositionRiskItem],
        )
        for pos in positions:
            if pos.position_amt != 0.0:
                side: str = "SELL" if pos.position_amt > 0 else "BUY"
                qty: float = abs(pos.position_amt)
                order_params = self._signed_params(
                    {
                        "symbol": pos.symbol,
                        "side": side,
                        "type": "MARKET",
                        "quantity": qty,
                        "reduceOnly": "true",
                    }
                )
                self.send_sync(
                    "POST",
                    "/fapi/v1/order",
                    params=order_params,
                    headers=self._auth_headers(),
                )
        return True
