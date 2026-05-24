from datetime import datetime, timezone
from typing import overload

from numpy import float64, int64
from numpy.typing import NDArray

from core import constant as c
from core.configurations import ConfigurationFootprint, ConfigurationStrategy


class FPconverter:
    def __init__(
        self,
        footprint: NDArray[int64],
        headers: NDArray[int64],
        trade_param: memoryview,
        cfgFP: ConfigurationFootprint,
    ) -> None:
        self.footprint, self.headers = footprint, headers
        self.trade_par = trade_param
        self.fpLines, self.fpCols = cfgFP.fpLines, cfgFP.fpCols
        self.fpPanelCols, self.barCount = cfgFP.fpPanelCols, cfgFP.bar_count
        self.ims = cfgFP.intervalMs
        self.idxVP, self.idxDP = cfgFP.colVP, cfgFP.colDP

        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult: float = (10**self.pricePrec) + 1e-9
        self.qtyMult: float = 10**self.qtyPrec + 1e-9

    def init_session(self, price: float | int, timestamp: int):
        self.nBasePrice: int = (
            self.to_nPrice(price) if isinstance(price, float) else price
        )
        self.baseTimestamp: int = timestamp - (timestamp % self.ims)
        self.center: int = self.fpLines // 2

    @overload
    def to_idy(self, nPrice: int) -> int | None: ...
    @overload
    def to_idy(self, nPrice: int64) -> int64: ...
    def to_idy(self, nPrice):
        idy: int | int64 = (self.nBasePrice - nPrice) + self.center
        if 0 <= idy < self.fpLines:
            return idy
        else:
            return None

    def to_idx(self, timestamp: int, is_sell: bool) -> int | None:
        idx: int = (timestamp - self.baseTimestamp) // self.ims * 2 + (
            0 if is_sell else 1
        )
        if 0 <= idx < self.fpCols:
            return idx
        else:
            return None

    @overload
    def to_nPrice(self, value: float) -> int: ...
    @overload
    def to_nPrice(self, value: int | int64) -> int | int64: ...
    def to_nPrice(self, value):
        if isinstance(value, float):
            return round(value * self.priceMult)
        else:
            return (self.center - value) + self.nBasePrice

    def to_nQty(self, qty: float) -> int:
        return round(qty * self.qtyMult)

    def to_price(self, nPrice: int | int64) -> float | float64:
        return nPrice / self.priceMult

    def to_qty(self, nQty: int | int64) -> float | float64:
        return nQty / self.qtyMult

    def to_strftime(self, timestamp_ms: int | int64) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H-%M-%S"
        )

    def get_price(self, idy: int | int64) -> float:
        return round(
            self.to_price(self.to_nPrice(idy)),
            ndigits=self.pricePrec,
        )

    def get_qty(self, idy: int, idx: int) -> float:
        return self.to_qty(self.footprint[idy, idx])

    @overload
    def get_time(self, idx: int64, strftime: bool = False) -> int64: ...
    @overload
    def get_time(self, idx: int, strftime: bool = True) -> str: ...
    def get_time(self, idx: int | int64, strftime: bool = False):
        if strftime:
            return self.to_strftime((idx & ~1) // 2 * self.ims + self.baseTimestamp)
        else:
            return (idx & ~1) // 2 * self.ims + self.baseTimestamp

    # Headers
    def _get_header(self, idx: int | int64, header: c.BarHeaders) -> int64:
        return self.headers[(idx & ~1) // 2, header]

    # OHLC
    def openNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Open)

    def highNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.High)

    def lowNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Low)

    def closeNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Close)

    def openTime(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.OpenTime)

    def lastTradeTime(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.LastTradeTime)

    # Indicators
    def countTrade(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.CountTrade)

    def volume(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Volume)

    def delta(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Delta)

    def cvd(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.CVD)

    def vwap(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VWAP)

    def vwap_bb_lower(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VWAP_BB_LOWER)

    def vwap_bb_upper(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VWAP_BB_UPPER)

    def atr(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.ATR)

    def poc(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.POC)

    def vah(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VAH)

    def val(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VAL)

    # Other
    def time_ms(self, idx: int | int64) -> int:
        return int(self.lastTradeTime(idx) // 1_000_000)


class TradeConverter:
    def __init__(
        self, trade_param: memoryview, cfgStrategy: ConfigurationStrategy
    ) -> None:
        self.trade_param = trade_param

        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = trade_param[:]
        self.priceMult: float = (10**self.pricePrec) + 1e-9
        self.qtyMult: float = 10**self.qtyPrec + 1e-9

        self.cfgST = cfgStrategy
        self.latencyMs: int = self.cfgST.latency
        self.leverage: int = self.cfgST.leverage
        self.slipage: int = self.cfgST.slipage
        self._entryQty: int = self.cfgST.entryQty
        self._tpDev: int = self.cfgST.TPdev
        self._slDev: int = self.cfgST.SLdev
        self._maxLockNbalance: int = self.cfgST.maxLockBalance
        self._maxLossNbalance: int = self.cfgST.maxLossBalance
        self._scalePrec: int = self.cfgST.scalePrec
        self.scale: int = round(10**self._scalePrec)
        self.startNbalance: int = 0
        self._nBalance: int = 0
        self._lockedNbalance: int = 0
        self.minOrderNsize: int = 0
        self.takerNcommission: int = 0
        self.makerNcommission: int = 0
        self._unrealizedNpnl: int = 0
        self.longUnrealizedNpnl: int = 0
        self.shortUnrealizedNpnl: int = 0
        self.last_order_id: int = 0
        self.longNqty: int = 0
        self.longEntryNprice: int = 0
        self.longWeight: int = 0
        self.longPweight: int = 0
        self.shortNqty: int = 0
        self.shortEntryNprice: int = 0
        self.shortWeight: int = 0
        self.shortPweight: int = 0

    def init_session(
        self,
        startBalance: float,
        minOrderSize: float,
        takerCommission: float,
        makerCommission: float,
    ) -> None:
        self.startNbalance = round(startBalance * self.scale)
        self.minOrderNsize = round(minOrderSize * self.scale)
        self.takerNcommission = round(takerCommission * 10000)
        self.makerNcommission = round(makerCommission * 10000)

        self.nBalance = self.startNbalance

    @property
    def nBalance(self) -> int:
        return self._nBalance

    @nBalance.setter
    def nBalance(self, nValue: int) -> None:
        self._nBalance += nValue
        if not self.lossNbalanceSafeLimit:
            raise RuntimeError

    @property
    def lockedNbalance(self) -> int:
        return self._lockedNbalance

    @lockedNbalance.setter
    def lockedNbalance(self, nValue: int) -> None:
        self._lockedNbalance += nValue

    @property
    def availableNbalance(self) -> int:
        return self.nBalance - self.lockedNbalance

    @property
    def lossNbalanceSafeLimit(self) -> bool:
        return self.nBalance > (
            self.startNbalance - (self.startNbalance * self._maxLossNbalance // 1000)
        )

    @property
    def lockedNbalanceSafeLimit(self) -> bool:
        return self.lockedNbalance < (self._nBalance * self._maxLockNbalance // 1000)

    @property
    def nominalEntryNqty(self) -> int:
        return self.availableNbalance * self._entryQty // 1000

    @property
    def nominalEntryNqtyWithLeverage(self) -> int | None:
        if (qty := (self.leverage * self.nominalEntryNqty)) > self.minOrderNsize:
            return qty

    def entryNqtyWithLeverage(self, nPrice: int, nominalNqty: int) -> int:
        return nominalNqty * self.scale // nPrice

    @property
    def newOrderId(self) -> int:
        self.last_order_id += 1
        return self.last_order_id

    def nPriceWithSlippage(self, nPrice: int, is_buy: bool) -> int:
        slipageTicks = nPrice * self.slipage // 10_000
        return nPrice + (slipageTicks if is_buy else -slipageTicks)

    def TPdevNprice(self, nPrice: int, is_long: bool) -> int:
        tpTicks: int = nPrice * self._tpDev // 1000
        return nPrice + (tpTicks if is_long else -tpTicks)

    def SLdevNprice(self, nPrice: int, is_long: bool) -> int:
        slTicks: int = nPrice * self._slDev // 1000
        return nPrice + (-slTicks if is_long else slTicks)

    def to_nMargin(self, nPrice: int, nQty: int) -> int:
        return (nQty * nPrice) // self.scale // self.leverage

    def to_nPnl(self, closeNprice: int, nQty: int, is_long: bool) -> int:
        diffNprice: int = (
            closeNprice - (self.longEntryNprice if is_long else self.shortEntryNprice)
        ) * (1 if is_long else -1)
        return diffNprice * nQty // self.scale

    @property
    def unrealizedNpnl(self) -> int:
        return self._unrealizedNpnl

    @unrealizedNpnl.setter
    def unrealizedNpnl(self, lastNprice: int) -> None:
        if self.shortNqty or self.longNqty:
            self.longUnrealizedNpnl = (
                self.to_nPnl(lastNprice, self.longNqty, True) if self.longNqty else 0
            )
            self.shortUnrealizedNpnl = (
                self.to_nPnl(lastNprice, self.shortNqty, False) if self.shortNqty else 0
            )
            self._unrealizedNpnl = self.longUnrealizedNpnl + self.shortUnrealizedNpnl
        else:
            self._unrealizedNpnl = 0

    def to_nCommission(self, nQty: int, is_maker: bool) -> int:
        return (
            nQty * (self.makerNcommission if is_maker else self.takerNcommission)
        ) // 1000

    def to_nPrice(self, price: float | int) -> int:
        if isinstance(price, float):
            return round(price * self.scale)
        else:
            return price * (10 ** (self._scalePrec - self.pricePrec))

    def to_nQty(self, qty: float | int) -> int:
        if isinstance(qty, float):
            return round(qty * self.scale)
        else:
            return qty * (10 ** (self._scalePrec - self.qtyPrec))

    def to_price(self, nPrice: int) -> float:
        return round((nPrice / self.scale), self.pricePrec)

    def to_qty(self, nQty: int) -> float:
        return round((nQty / self.scale), self.qtyPrec)

    def to_strftime(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def to_roi(self, nPnl: int, nMargin: int) -> float:
        return (nPnl / nMargin) * 100
