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

        self._nBalance: memoryview = memoryview(bytearray(8)).cast("q")
        self._lockedNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self._availableNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self._longNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self._longEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")
        self._shortNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self._shortEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")

        self._unrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self._longUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self._shortUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")

        self._nBalance[0] = self.startNbalance

        self._client_order_id: int = 0

        self.oh_rows: int = 10_000
        self.oh_cols: int = c.TP_ConstantCount

        self._init_array()

    def _init_array(self) -> None:
        self.orders_history: NDArray[int64] = np.ndarray(
            shape=(self.oh_rows, self.oh_cols), dtype=int64
        )
        self.orders_history.fill(0)
        self.ohWid: memoryview = memoryview(bytearray(8)).cast("q")

    def init_session(
        self,
        nBalance: memoryview,
        lockedNbalance: memoryview,
        availableNbalance: memoryview,
        longNqty: memoryview,
        longEntryNprice: memoryview,
        shortNqty: memoryview,
        shortEntryNprice: memoryview,
        unrealizedNpnl: memoryview,
        longUnrealizedNpnl: memoryview,
        shortUnrealizedNpnl: memoryview,
    ) -> None:
        self._nBalance = nBalance
        self._lockedNbalance = lockedNbalance
        self._availableNbalance = availableNbalance
        self._longNqty = longNqty
        self._longEntryNprice = longEntryNprice
        self._shortNqty = shortNqty
        self._shortEntryNprice = shortEntryNprice

        self._unrealizedNpnl = unrealizedNpnl
        self._longUnrealizedNpnl = longUnrealizedNpnl
        self._shortUnrealizedNpnl = shortUnrealizedNpnl

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
        return self._nBalance[0]

    @property
    def lockedNbalance(self) -> int:
        return self._lockedNbalance[0]

    @property
    def availableNbalance(self) -> int:
        return self._availableNbalance[0]

    @property
    def lossNbalanceSafeLimit(self) -> bool:
        return self.nBalance > (
            self.startNbalance - (self.startNbalance * self._maxLossNbalance // 10_000)
        )

    @property
    def lockedNbalanceSafeLimit(self) -> bool:
        return self.lockedNbalance < (self.nBalance * self._maxLockNbalance // 10_000)

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
        self._client_order_id += 1
        return self._client_order_id

    @property
    def unrealizedNpnl(self) -> int:
        return self._unrealizedNpnl[0]

    @property
    def longUnrealizedNpnl(self) -> int:
        return self._longUnrealizedNpnl[0]

    @property
    def shortUnrealizedNpnl(self) -> int:
        return self._shortUnrealizedNpnl[0]

    def TPdevNprice(self, nPrice: int, is_long: bool) -> int:
        tpTicks: int = nPrice * self._tpDev // 10_000
        return nPrice + (tpTicks if is_long else -tpTicks)

    def SLdevNprice(self, nPrice: int, is_long: bool) -> int:
        slTicks: int = nPrice * self._slDev // 10_000
        return nPrice + (-slTicks if is_long else slTicks)

    def is_averaging(self, order_param: int) -> bool:
        if bool(order_param & c.OF_LONG):
            return True if self._longNqty[0] else False
        else:
            return True if self._shortNqty[0] else False

    def final_action(self) -> None:
        if self.cfgAC.save_orders_history:
            np.save(c.ORDERS_HISTORY_DUMP_PATH, self.orders_history[: self.ohWid[0], :])
