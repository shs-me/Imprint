from datetime import datetime, timezone

from ....configurations import cfgAccount


class TradeConverter:
    def __init__(
        self,
        cfgAcount: cfgAccount,
        price_prec: int,
        qty_prec: int,
    ) -> None:
        self.pricePrec, self.qtyPrec = price_prec, qty_prec
        self.priceMult: int = 10**self.pricePrec
        self.qtyMult: int = 10**self.qtyPrec

        self.cfgAC = cfgAcount
        self._entryQty: int = self.cfgAC.entry_qty
        self._tpDev: int = self.cfgAC.tp_dev
        self._slDev: int = self.cfgAC.sl_dev
        self._maxLockNbalance: int = self.cfgAC.max_lock_balance
        self._maxLossNbalance: int = self.cfgAC.max_loss_balance
        self._scalePrec: int = self.cfgAC.scale_prec
        self.latency: int = self.cfgAC.latency
        self.leverage: int = self.cfgAC.leverage

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
        self.shortNqty: int = 0
        self.shortEntryNprice: int = 0

    def init_session(
        self,
        startBalance: float,
        minOrderSize: float,
        takerCommission: float,
        makerCommission: float,
    ) -> None:
        self.startNbalance = round(startBalance * self.scale)
        self.minOrderNsize = round(minOrderSize * self.scale)
        self.takerNcommission = round(takerCommission * 10_000)
        self.makerNcommission = round(makerCommission * 10_000)

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
        nominal_qty: float = nominalNqty / self.scale
        return round((nominal_qty * self.priceMult * self.qtyMult) / nPrice)

    @property
    def newClientOrderId(self) -> int:
        self.last_order_id += 1
        return self.last_order_id

    def TPdevNprice(self, nPrice: int, is_long: bool) -> int:
        tpTicks: int = nPrice * self._tpDev // 1000
        return nPrice + (tpTicks if is_long else -tpTicks)

    def SLdevNprice(self, nPrice: int, is_long: bool) -> int:
        slTicks: int = nPrice * self._slDev // 1000
        return nPrice + (-slTicks if is_long else slTicks)

    def to_nMargin(self, nPrice: int, nQty: int) -> int:
        margin: float = (
            (nQty * self.qtyMult) * (nPrice * self.priceMult)
        ) / self.leverage
        return round(margin * self.scale)

    def to_nPnl(self, closeNprice: int, nQty: int, is_long: bool) -> int:
        entryNprice: int = self.longEntryNprice if is_long else self.shortEntryNprice
        diffNprice: int = (closeNprice - entryNprice) * (1 if is_long else -1)
        pnl: float = (diffNprice / self.priceMult) * (nQty / self.qtyMult)
        return round(pnl * self.scale)

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
            self.shortUnrealizedNpnl = 0
            self.longUnrealizedNpnl = 0

    def to_nCommission(self, nQty: int, is_maker: bool) -> int:
        rate: int = self.makerNcommission if is_maker else self.takerNcommission
        commission: float = (nQty / self.qtyMult) * (rate / 10_000)
        return round(commission * self.scale)

    def to_roi(self, nPnl: int, nMargin: int) -> float:
        return (nPnl / nMargin) * 100

    def to_strftime(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
