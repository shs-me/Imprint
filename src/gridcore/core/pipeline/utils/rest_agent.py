"""Exchange REST API client implementation integrated with Connector config."""

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import msgspec
from loguru import logger

from ...configs import Connector


class RestAgent:
    """REST client providing symbol metadata, account balances, and order management methods."""

    def __init__(self, symbol: str, connector: Connector) -> None:
        self.symbol: str = symbol.upper()
        self.connector: Connector = connector

        self.base_url: str = self.connector.base_uri_for_rest
        self.api_key: str = os.getenv("API_KEY", "")
        self.secret_key: str = os.getenv("SECRET_KEY", "")
        if self.api_key == "" or self.secret_key == "":
            raise RuntimeError("API_KEY or SECRET_KEY not found")

        self._symbol_info: dict[str, Any] | None = None

    def _sign_query(self, params: dict[str, Any]) -> str:
        """Appends timestamp and generates HMAC SHA256 signature for private endpoints."""
        params["timestamp"] = int(time.time() * 1000)
        query_str = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query_str}&signature={signature}"

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        """Executes HTTP request to exchange REST API and decodes response using msgspec."""
        params = params or {}
        url = f"{self.base_url}/{endpoint}"

        if signed:
            query = self._sign_query(params)
        else:
            query = urlencode(params) if params else ""

        headers = {"User-Agent": "GridCore/1.0"}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        req_data = None
        if method.upper() in ("GET", "DELETE"):
            if query:
                url = f"{url}?{query}"
        elif method.upper() in ("POST", "PUT"):
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            req_data = query.encode("utf-8")

        req = Request(url=url, data=req_data, headers=headers, method=method.upper())

        try:
            with urlopen(req, timeout=10) as resp:
                raw_body = resp.read()
                return msgspec.json.decode(raw_body)
        except Exception as e:
            raise RuntimeError(f"RestAgent Request Error [{method} {endpoint}]: {e}")

    def get_exchange_info(self) -> dict[str, Any]:
        """Fetches and caches symbol metadata from /fapi/v1/exchangeInfo."""
        if self._symbol_info is None:
            data = self._request("GET", "/fapi/v1/exchangeInfo")
            for sym in data.get("symbols", []):
                if sym.get("symbol") == self.symbol:
                    self._symbol_info = sym
                    break
            if self._symbol_info is None:
                raise ValueError(f"Symbol {self.symbol} not found in exchangeInfo")

        return self._symbol_info

    def get_tick_size(self) -> str:
        """Fetches minimum tick size increment for target symbol."""
        try:
            info = self.get_exchange_info()
            for f in info.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    return f.get("tickSize", "0.01")
        except Exception as e:
            logger.warning(f"Failed to fetch tick_size via REST: {e}. Fallback to 0.01")
        return "0.01"

    def get_lot_size(self) -> str:
        """Fetches minimum lot size increment for target symbol."""
        try:
            info = self.get_exchange_info()
            for f in info.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    return f.get("stepSize", "0.001")
        except Exception as e:
            logger.warning(f"Failed to fetch lot_size via REST: {e}. Fallback to 0.001")
        return "0.001"

    def get_min_order_size_usdt(self) -> float:
        """Fetches minimum required order nominal size in USDT/Quote currency."""
        try:
            info = self.get_exchange_info()
            for f in info.get("filters", []):
                if f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
                    return float(f.get("notional", f.get("minNotional", 5.0)))
        except Exception as e:
            logger.warning(
                f"Failed to fetch min_order_size via REST: {e}. Fallback to 5.0"
            )
        return 5.0

    def get_balance(self, free: bool = True) -> float:
        """Fetches available account equity balance."""
        try:
            account = self._request("GET", "/fapi/v2/account", signed=True)
            for asset in account.get("assets", []):
                if asset.get("asset") == "USDT":
                    return float(
                        asset.get("availableBalance" if free else "marginBalance", 0.0)
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch balance via REST: {e}. Fallback to 1000.0")
        return 1000.0

    def get_commission(self, is_maker: bool = True) -> float:
        """Fetches maker or taker commission rate for account."""
        try:
            account = self._request("GET", "/fapi/v2/account", signed=True)
            key = "makerCommissionRate" if is_maker else "takerCommissionRate"
            if key in account:
                return float(account[key])
        except Exception as e:
            logger.warning(
                f"Failed to fetch commission via REST: {e}. Fallback to default."
            )
        return 0.002 if is_maker else 0.005

    def cancel_all_orders(
        self,
        symbol: str | None = None,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels active order via REST endpoint /fapi/v1/order."""
        params: dict[str, Any] = {"symbol": (symbol or self.symbol).upper()}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

    def close_all_positions(self) -> None:
        pass
