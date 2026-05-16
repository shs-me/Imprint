import numpy as np
from numpy import object_
from numpy.typing import NDArray

from core import constant as c
from core.engine.agents_utils.utils import TradeConverter
from core.settings import ClosePosition, OpenPosition, OrderFlag
from core.utils.monitoring.agent_manager import AgentManager


class TradeManager:
    def __init__(self, manager: AgentManager, converter: TradeConverter) -> None:
        self.manager: AgentManager = manager
        self.con: TradeConverter = converter

        # Strategy
        self.lines: int = self.con.cfgST.tradesLines
        self.cols: int = self.con.cfgST.tradesCols
        self._init_array()

        # Variable's
        self.openPositions: dict[str, OpenPosition] = {}
        self.closePositions: dict[int, ClosePosition] = {}

    def _init_array(self) -> None:
        self.orders_history: NDArray[object_] = np.ndarray(
            shape=(self.lines, self.cols), dtype=object_
        )
        self.active_orders: NDArray[object_] = np.ndarray(
            shape=(self.lines, c.AO_ConstantCount, 2), dtype=object_
        )

        self.ohRRow: memoryview = memoryview(bytearray(8)).cast("q")
        self.ohWRow: memoryview = memoryview(bytearray(8)).cast("q")
        self.aoWRow: memoryview = memoryview(bytearray(8)).cast("q")

    def update_orders_array(
        self,
        nPrice: int,
        nQty: int,
        timestamp: int,
        orderParam: int,
        nCommission: int | None,
        orderID: int | None,
    ) -> None:
        ohWRow, aoWRow = self.ohWRow, self.aoWRow
        oh, ao = self.orders_history, self.active_orders
        # - - -
        oh[ohWRow[0], c.TP_nPrice] = nPrice
        oh[ohWRow[0], c.TP_nQty] = nQty
        oh[ohWRow[0], c.TP_timestamp] = timestamp
        oh[ohWRow[0], c.TP_orderParam] = orderParam
        oh[ohWRow[0], c.TP_commission] = nCommission
        oh[ohWRow[0], c.TP_orderID] = orderID if orderID else self.con.newOrderId
        ohWRow[0] += 1
        if bool(orderParam & c.OF_NEW):
            side, row = (0, 0) if bool(orderParam & c.OF_LIMIT) else (1, 1)
            wRow = aoWRow[0]
            ao[wRow, c.AO_nPrice, side] = nPrice
            ao[wRow, c.AO_nQty, side] = nQty
            ao[wRow, c.AO_timestamp, side] = timestamp
            ao[wRow, c.AO_orderParam, side] = orderParam
            ao[wRow, c.AO_orderID, side] = orderID if orderID else self.con.newOrderId
            aoWRow[0] += row

    def prepare_trades(self) -> None:
        ohRRow, ohWRow, aoWRow = self.ohRRow, self.ohWRow, self.aoWRow
        oh, ao, _ = self.orders_history, self.active_orders, self.con
        op, cp = self.openPositions, self.closePositions
        # - - -
        while ohRRow[0] != ohWRow[0]:
            rRow, wRow = ohRRow[0], ohWRow[0]

            nPrice: int = oh[rRow, c.TP_nPrice]
            nQty: int = oh[rRow, c.TP_nQty]
            timestamp: int = oh[rRow, c.TP_timestamp]
            orderParam: int = oh[rRow, c.TP_orderParam]
            commission: int = oh[rRow, c.TP_commission]
            orderID: int = oh[rRow, c.TP_orderID]

            nMargin: int = _.to_margin(nPrice=nPrice, nQty=nQty)
            # print(nMargin, nPrice, nQty, rRow, oh[rRow, :])
            time: str = _.to_strftime(timestamp)
            # Position Side
            is_long: bool = bool(orderParam & OrderFlag.LONG)
            is_short: bool = bool(orderParam & OrderFlag.SHORT)
            # Side
            is_buy: bool = bool(orderParam & OrderFlag.BUY)
            is_sell: bool = bool(orderParam & OrderFlag.SELL)
            # Status
            is_new: bool = bool(orderParam & OrderFlag.NEW)
            is_filled: bool = bool(orderParam & OrderFlag.FILLED)
            is_canceled: bool = bool(orderParam & OrderFlag.CANCELED)

            lockBalance: int = 0
            balance: int = 0
            if is_filled:
                position = "LONG" if is_long else "SHORT"
                if (is_buy and is_long) or (is_sell and is_short):
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
                    op[position]["nominalNcommission"] += commission
                    op[position]["entryNpriceWeight"] += nQty
                    op[position]["entryNpricePWeight"] += nPrice * nQty
                    op[position]["entryNprice"] = (
                        op[position]["entryNpricePWeight"]
                        // op[position]["entryNpriceWeight"]
                    )

                    lockBalance, balance = nMargin, 0

                elif (is_sell and is_long) or (is_buy and is_short):
                    price: float = _.to_price(nPrice)
                    qty: float = _.to_qty(nQty)
                    eNprice: int = op[position]["entryNprice"]
                    _nMargin: int = _.to_margin(nPrice=eNprice, nQty=nQty)
                    nPnl: int = _.to_nPnl(
                        closeNprice=nPrice,
                        entryNprice=eNprice,
                        is_long=is_long,
                        nQty=nQty,
                        nCommission=commission,
                    )
                    side = "TakeProfits" if (nPnl > 0) else "StopLosses"
                    pnl: float = nPnl / _.scale
                    roi = _.to_nRoi(nPnl, _nMargin) / 100

                    op[position]["realizedPNL"] += pnl
                    op[position]["realizedROI"] += roi
                    op[position]["tempNqty"] -= nQty

                    op[position][side] = {
                        rRow: {
                            "time": time,
                            "entryPrice": price,
                            "commission": _.to_qty(commission),
                            "qtyUSD": price * qty,
                            "qty": qty,
                            "realizedPNL": pnl,
                            "realizedROI": roi,
                        }
                    }

                    if op[position]["tempNqty"] == 0:
                        temp = op.pop(position)
                        cp[rRow] = {
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

            elif is_new and ((is_buy and is_long) or (is_sell and is_short)):
                lockBalance, balance = nMargin, 0

            elif is_canceled and ((is_buy and is_long) or (is_sell and is_short)):
                lockBalance, balance = -nMargin, 0

            _.lockedNbalance = lockBalance
            _.nBalance = balance

            ohRRow[0] += 1
