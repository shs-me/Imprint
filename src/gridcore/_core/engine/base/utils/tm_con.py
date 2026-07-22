from datetime import datetime, timezone

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from .... import configurations as cfg
from .... import constant as c


class TradeConverter:
    def __init__(
        self,
        cfgAccount: cfg.Account,
        cfgStrategy: cfg.Strategy,
        price_prec: int,
        qty_prec: int,
    ) -> None:
        self.pricePrec, self.qtyPrec = price_prec, qty_prec
        self.priceMult: int = 10**self.pricePrec
        self.qtyMult: int = 10**self.qtyPrec

        self.cfgST = cfgStrategy
        self._entryQty: int = self.cfgST.entry_qty
        self._tpDev: int = self.cfgST.tp_dev
        self._slDev: int = self.cfgST.sl_dev
        self._maxLockNbalance: int = self.cfgST.max_lock_balance
        self._maxLossNbalance: int = self.cfgST.max_loss_balance

        self.cfgAC = cfgAccount
        self._scalePrec: int = self.cfgAC.scale_prec
        self.scale: int = 10**self._scalePrec
        self.latency: int = self.cfgAC.latency_ms
        self.leverage: int = self.cfgAC.leverage
        self.startNbalance: int = round(self.cfgAC.balance * self.scale)
        self.minOrderNsize: int = round(self.cfgAC.min_order_size * self.scale)
        self.takerNcommission: int = self.cfgAC.taker_commission
        self.makerNcommission: int = self.cfgAC.maker_commission

        self._nBalance: int = 0
        self._lockedNbalance: int = 0
        self._unrealizedNpnl: int = 0
        self.longUnrealizedNpnl: int = 0
        self.shortUnrealizedNpnl: int = 0
        self.last_order_id: int = 0
        self.longNqty: int = 0
        self.longEntryNprice: int = 0
        self.shortNqty: int = 0
        self.shortEntryNprice: int = 0

        self.nBalance = self.startNbalance

        self.oh_rows: int = 10_000
        self.oh_cols: int = c.TP_ConstantCount

        self._init_array()

    def _init_array(self) -> None:
        self.orders_history: NDArray[int64] = np.ndarray(
            shape=(self.oh_rows, self.oh_cols), dtype=int64
        )
        self.orders_history.fill(0)
        self.ohWid: memoryview = memoryview(bytearray(8)).cast("q")

    def update_orders_history(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        ohWid, oh = self.ohWid, self.orders_history
        # - - -
        oh[ohWid[0], c.TP_timestamp] = timestamp
        oh[ohWid[0], c.TP_orderParam] = order_param
        oh[ohWid[0], c.TP_orderID] = order_id
        oh[ohWid[0], c.TP_nPrice] = nPrice
        oh[ohWid[0], c.TP_nQty] = nQty
        oh[ohWid[0], c.TP_commission] = nCommission
        ohWid[0] += 1
        if ohWid[0] >= oh.shape[0]:
            old_rows: int = oh.shape[0]
            self.orders_history = np.resize(
                oh, new_shape=((old_rows + self.oh_rows), self.oh_cols)
            )
            self.orders_history[old_rows:, :] = 0

    @property
    def nBalance(self) -> int:
        return self._nBalance

    @nBalance.setter
    def nBalance(self, nValue: int) -> None:
        self._nBalance += nValue
        if not self.lossNbalanceSafeLimit:
            raise RuntimeError(
                (
                    f"Loss balance > safe limit "
                    f"Start balance: {self.startNbalance / self.scale} "
                    f"Balance: {self.nBalance / self.scale}"
                )
            )

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
            self.startNbalance - (self.startNbalance * self._maxLossNbalance // 10_000)
        )

    @property
    def lockedNbalanceSafeLimit(self) -> bool:
        return self.lockedNbalance < (self._nBalance * self._maxLockNbalance // 10_000)

    @property
    def nominalEntryNqty(self) -> int:
        return self.availableNbalance * self._entryQty // 10_000

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
        tpTicks: int = nPrice * self._tpDev // 10_000
        return nPrice + (tpTicks if is_long else -tpTicks)

    def SLdevNprice(self, nPrice: int, is_long: bool) -> int:
        slTicks: int = nPrice * self._slDev // 10_000
        return nPrice + (-slTicks if is_long else slTicks)

    def to_nMargin(self, nPrice: int, nQty: int) -> int:
        margin: float = (
            (nQty / self.qtyMult) * (nPrice / self.priceMult)
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

    def to_nCommission(self, nPrice: int, nQty: int, is_maker: bool) -> int:
        rate: int = self.makerNcommission if is_maker else self.takerNcommission
        commission: float = (
            ((nPrice / self.priceMult) * (nQty / self.qtyMult)) * rate / 10_000
        )
        return round(commission * self.scale)

    def to_roi(self, nPnl: int, nMargin: int) -> float:
        return (nPnl / nMargin) * 100

    def to_strftime(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def is_averaging(self, order_param: int) -> bool:
        if bool(order_param & c.OF_LONG):
            return True if self.longNqty else False
        else:
            return True if self.shortNqty else False

    def final_action(self) -> None:
        if self.cfgAC.save_orders_history:
            np.save(c.ORDERS_HISTORY_DUMP_PATH, self.orders_history[: self.ohWid[0], :])
