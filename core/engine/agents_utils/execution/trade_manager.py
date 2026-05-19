import numpy as np
from numpy import object_
from numpy.typing import NDArray

from core.engine.agents_utils.utils import TradeConverter
from core.settings import ClosePosition, OpenPosition, OrderFlag
from core.utils.monitoring.agent_manager import AgentManager

OPEN_ORDER: int = 0
TP_ORDER: int = 1
SL_ORDER: int = 2


class TradeManager:
    def __init__(self, manager: AgentManager, converter: TradeConverter) -> None:
        self.manager: AgentManager = manager
        self.con: TradeConverter = converter

        self.ohLines = self.con.cfgST.ordersHistoryLines
        self.ohCols = self.con.cfgST.ordersHistoryCols
        self.aoLines = self.con.cfgST.activeOrdersLines
        self.aoCols = self.con.cfgST.activeOrdersCols
        self._init_array()

        # Variable's
        self.openPositions: dict[str, OpenPosition] = {}
        self.closePositions: dict[int, ClosePosition] = {}

    def _init_array(self) -> None:
        self.orders_history: NDArray[object_] = np.ndarray(
            shape=(self.ohLines, self.ohCols), dtype=object_
        )
        self.active_orders: NDArray[object_] = np.ndarray(
            shape=(3, self.aoLines, self.aoCols), dtype=object_
        )

        self.ohRRow: memoryview = memoryview(bytearray(8)).cast("q")
        self.ohWRow: memoryview = memoryview(bytearray(8)).cast("q")
        self.aoWRow: memoryview = memoryview(bytearray(8)).cast("q")

    def update_orders_history(
        self,
        nPrice: int,
        nQty: int,
        timestamp: int,
        orderParam: int,
        orderID: int | None,
        nCommission: int = 0,
    ) -> None:
        ohWRow, oh, _ = self.ohWRow, self.orders_history, self.con
        # - - -
        order_param: list[int] = [nPrice, nQty, timestamp, orderParam, nCommission]
        order_param.append(orderID if (orderID is not None) else _.newOrderId)
        oh[ohWRow[0], :] = order_param
        ohWRow[0] += 1
        if ohWRow[0] >= oh.shape[0]:
            oldLines = oh.shape[0]
            self.orders_history = np.resize(
                oh, new_shape=((oldLines + self.ohLines), self.ohCols)
            )
            self.orders_history[oldLines - 1 :, :] = None

    def set_active_order(
        self,
        nPrice: int,
        nQty: int,
        timestamp: int,
        orderParam: int,
        orderID: int | None = None,
        openWrow: int | None = None,
        is_tp: bool = True,
    ) -> None:
        _, ao, aoWRow = self.con, self.active_orders, self.aoWRow
        # - - -
        order_param: list[int] = [nPrice, nQty, timestamp, orderParam]
        order_param.append(orderID if (orderID is not None) else _.newOrderId)
        if openWrow is None:
            ao[OPEN_ORDER, aoWRow[0], :] = order_param
            aoWRow[0] += 1
            if aoWRow[0] >= ao.shape[1]:
                oldLines = ao.shape[1]
                self.active_orders = np.resize(
                    ao, new_shape=(3, (oldLines + self.aoLines), self.aoCols)
                )
                self.active_orders[:, oldLines - 1 :, :] = None
        else:
            ao[(TP_ORDER if is_tp else SL_ORDER), openWrow, :] = order_param

        self.update_orders_history(nPrice, nQty, timestamp, orderParam, None)

    def prepare_trades(self) -> None:
        nPrice: int
        nQty: int
        timestamp: int
        orderParam: int
        nCommission: int
        orderID: int

        oh, ohRRow, ohWRow = self.orders_history, self.ohRRow, self.ohWRow
        _, op, cp = self.con, self.openPositions, self.closePositions
        # - - -
        while ohRRow[0] != ohWRow[0]:
            nPrice, nQty, timestamp, orderParam, nCommission, orderID = oh[ohRRow[0], :]
            is_long: bool = bool(orderParam & OrderFlag.LONG)
            is_buy: bool = bool(orderParam & OrderFlag.BUY)

            is_new: bool = bool(orderParam & OrderFlag.NEW)
            is_filled: bool = bool(orderParam & OrderFlag.FILLED)
            is_canceled: bool = bool(orderParam & OrderFlag.CANCELED)

            is_open: bool = (is_buy and is_long) or (not is_buy and not is_long)
            nMargin: int = _.to_margin(nPrice=nPrice, nQty=nQty)
            lockBalance, balance = 0, 0
            if is_filled:
                time: str = _.to_strftime(timestamp)
                position = "LONG" if is_long else "SHORT"
                if is_open:
                    if op.get(position, None) is None:
                        op[position] = {
                            "positionSide": position,
                            "openTime": time,
                            "entryNprice": 0,
                            "entryNpriceWeight": 0,
                            "entryNpricePWeight": 0,
                            "nQuantity": 0,
                            "nominalNqty": 0,
                            "tempNqty": 0,
                            "nominalNcommission": 0,
                            "leverage": _.leverage,
                            "realizedPNL": 0.0,
                            "realizedROI": 0.0,
                            "TakeProfits": {},
                            "StopLosses": {},
                        }

                    op[position]["nQuantity"] += nQty
                    op[position]["nominalNqty"] += nPrice * nQty // _.scale
                    op[position]["tempNqty"] += nQty
                    op[position]["nominalNcommission"] += nCommission
                    op[position]["entryNpriceWeight"] += nQty
                    op[position]["entryNpricePWeight"] += nPrice * nQty
                    op[position]["entryNprice"] = (
                        op[position]["entryNpricePWeight"]
                        // op[position]["entryNpriceWeight"]
                    )

                else:
                    price: float = _.to_price(nPrice)
                    qty: float = _.to_qty(nQty)
                    eNprice: int = op[position]["entryNprice"]
                    _nMargin: int = _.to_margin(nPrice=eNprice, nQty=nQty)
                    nPnl: int = _.to_nPnl(
                        closeNprice=nPrice,
                        entryNprice=eNprice,
                        is_long=is_long,
                        nQty=nQty,
                        nCommission=nCommission,
                    )
                    side = "TakeProfits" if (nPnl > 0) else "StopLosses"
                    pnl: float = nPnl / _.scale
                    roi = _.to_nRoi(nPnl, _nMargin) / 100

                    op[position]["realizedPNL"] += pnl
                    op[position]["realizedROI"] += roi
                    op[position]["tempNqty"] -= nQty

                    op[position][side][orderID] = {
                        "price": price,
                        "qtyUSD": price * qty,
                        "qty": qty,
                        "realizedPNL": pnl,
                        "realizedROI": roi,
                        "commission": _.to_qty(nCommission),
                        "time": time,
                    }

                    if op[position]["tempNqty"] == 0:
                        temp = op.pop(position)
                        cp[orderID] = {
                            "positionSide": temp["positionSide"],
                            "openTime": temp["openTime"],
                            "closeTime": time,
                            "entryPrice": _.to_price(eNprice),
                            "closePrice": price,
                            "quantity": _.to_qty(temp["nQuantity"]),
                            "nominalQty": _.to_qty(temp["nominalNqty"]),
                            "nominalCommission": _.to_qty(temp["nominalNcommission"]),
                            "leverage": temp["leverage"],
                            "realizedPNL": temp["realizedPNL"],
                            "realizedROI": temp["realizedROI"],
                            "TakeProfits": temp["TakeProfits"],
                            "StopLosses": temp["StopLosses"],
                        }

                    lockBalance, balance = -_nMargin, nPnl

            elif is_new and is_open:
                lockBalance, balance = nMargin, 0

            elif is_canceled and is_open:
                lockBalance, balance = -nMargin, 0

            _.lockedNbalance = lockBalance
            _.nBalance = balance

            ohRRow[0] += 1
