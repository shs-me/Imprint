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
        self.weight: int = 0
        self.p_weight: int = 0

    def _init_array(self) -> None:
        self.orders_history: NDArray[object_] = np.ndarray(
            shape=(self.lines, self.cols), dtype=object_
        )
        self.active_orders: NDArray[object_] = np.ndarray(
            shape=(self.lines, c.AO_ConstantCount), dtype=object_
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
        oh[ohWRow[0], c.TP_orderID] = orderID if orderID else ohWRow[0]
        ohWRow[0] += 1
        if bool(orderParam & c.OF_NEW):
            ao[aoWRow[0], c.AO_nPrice] = nPrice
            ao[aoWRow[0], c.AO_nQty] = nQty
            ao[aoWRow[0], c.AO_timestamp] = timestamp
            ao[aoWRow[0], c.AO_orderParam] = orderParam
            ao[aoWRow[0], c.AO_orderID] = orderID if orderID else aoWRow[0]
            aoWRow[0] += 1

    def prepare_trades(self) -> None:
        ohRRow, ohWRow, aoWRow = self.ohRRow, self.ohWRow, self.aoWRow
        oh, ao, _ = self.orders_history, self.active_orders, self.con
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
                    if self.openPositions.get(position, None) is None:
                        self.openPositions[position] = {
                            "positionSide": position,
                            "openTime": time,
                            "entryNprice": 0,
                            "nQuantity": 0,
                            "nominalNqty": 0,
                            "tempNqty": 0,
                            "nominalNcommission": 0,
                            "laverage": self.con.leverage,
                            "realizedPNL": 0.0,
                            "realizedROI": 0.0,
                            "TakeProfits": {},
                            "StopLosses": {},
                        }

                    self.openPositions[position]["nQuantity"] += nQty
                    self.openPositions[position]["nominalNqty"] += nPrice * nQty
                    self.openPositions[position]["tempNqty"] += nQty
                    self.openPositions[position]["nominalNcommission"] += commission

                    self.weight = self.weight + nQty
                    self.p_weight = self.p_weight + (nPrice * nQty)
                    self.openPositions[position]["entryNprice"] = (
                        self.p_weight // self.weight
                    )

                    lockBalance, balance = nMargin, 0

                elif (is_sell and is_long) or (is_buy and is_short):
                    price: float = self.con.to_price(nPrice)
                    qty: float = self.con.to_qty(nQty)
                    eNprice: int = self.openPositions[position]["entryNprice"]
                    nPnl: int = self.con.to_nPnl(
                        closeNprice=nPrice,
                        entryNprice=eNprice,
                        is_long=is_long,
                        nQty=nQty,
                        nCommission=commission,
                    )
                    side = "TakeProfits" if (nPnl > 0) else "StopLosses"
                    pnl: float = nPnl / self.con.scale
                    roi = self.con.to_nRoi(nPnl, nMargin) / self.con.scale

                    self.openPositions[position]["realizedPNL"] += pnl
                    self.openPositions[position]["realizedROI"] += roi
                    self.openPositions[position]["tempNqty"] -= nQty

                    self.openPositions[position][side] = {
                        rRow: {
                            "time": time,
                            "entryPrice": price,
                            "commission": commission,
                            "qtyUSD": price * qty,
                            "qty": qty,
                            "realizedPNL": pnl,
                            "realizedROI": roi,
                        }
                    }

                    if self.openPositions[position]["tempNqty"] == 0:
                        temp = self.openPositions.pop(position)
                        self.closePositions[rRow] = {
                            "positionSide": temp["positionSide"],
                            "openTime": temp["openTime"],
                            "closeTime": time,
                            "entryPrice": self.con.to_price(eNprice),
                            "closePrice": price,
                            "quantity": self.con.to_qty(temp["nQuantity"]),
                            "nominalQty": self.con.to_qty(temp["nominalNqty"]),
                            "nominalCommission": self.con.to_qty(
                                temp["nominalNcommission"]
                            ),
                            "laverage": temp["laverage"],
                            "realizedPNL": temp["realizedPNL"],
                            "realizedROI": temp["realizedROI"],
                            "TakeProfits": temp["TakeProfits"],
                            "StopLosses": temp["StopLosses"],
                        }
                    lockBalance, balance = -nMargin, nPnl

            elif is_new and ((is_buy and is_long) or (is_sell and is_short)):
                lockBalance, balance = nMargin, 0

            elif is_canceled and ((is_buy and is_long) or (is_sell and is_short)):
                lockBalance, balance = -nMargin, 0

            _.setLockedNbalance(lockBalance)
            _.setNbalance(balance)

            ohRRow[0] += 1

    @property
    def have_active_orders(self) -> bool:
        return bool(np.any(self.active_orders[: self.aoWRow[0], 0]))
