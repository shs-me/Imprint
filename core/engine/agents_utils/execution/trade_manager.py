import numpy as np
from numpy import uint64
from numpy.typing import NDArray

from core.engine.agents_utils.utils import TradeConverter
from core.settings import ClosePosition, OpenPosition, OrderFlag
from core.utils.monitoring.agent_manager import AgentManager


class TradeManager:
    def __init__(self, manager: AgentManager, converter: TradeConverter) -> None:
        self.manager: AgentManager = manager
        self.con: TradeConverter = converter

        # Strategy
        self.lines: int = self.con.cfgST.lines
        self.cols: int = self.con.cfgST.cols
        self._init_array()

        # Variable's
        self.openPositions: dict[str, OpenPosition] = {}
        self.closePositions: dict[int, ClosePosition] = {}
        self.weight: int = 0
        self.p_weight: int = 0

    def _init_array(self) -> None:
        self.trades: NDArray[uint64] = np.ndarray(
            shape=(self.lines, self.cols),
            dtype=uint64,
        )

    def update_trades(
        self,
        orderID: int,
        timestamp: int,
        nPrice: int,
        nQty: int,
        commission: int,
        orderParam: OrderFlag,
    ) -> tuple[float, float]:
        oid: int = self.con.to_oid(orderID)
        self.trades[oid, :] = nPrice, nQty, timestamp, orderParam

        is_new = bool(orderParam & OrderFlag.NEW)
        is_filled = bool(orderParam & OrderFlag.FILLED)
        is_canceled = bool(orderParam & OrderFlag.CANCELED)
        is_long: bool = bool(orderParam & OrderFlag.LONG)
        is_short: bool = is_long is False
        is_buy: bool = bool(orderParam & OrderFlag.BUY)
        is_sell: bool = is_buy is False

        lockBalance: int = 0
        balance: int = 0
        nMargin: int = self.con.to_margin(nPrice=nPrice, nQty=nQty)
        time: str = self.con.to_strftime(timestamp)
        if is_filled:
            position = "LONG" if is_long else "SHORT"
            if is_buy and is_long or is_sell and is_short:
                lockBalance, balance = self.open_position(
                    position=position,
                    time=time,
                    nPrice=nPrice,
                    nQty=nQty,
                    commission=commission,
                    nMargin=nMargin,
                )
            elif is_sell and is_long or is_buy and is_short:
                lockBalance, balance = self.close_position(
                    oid=oid,
                    position=position,
                    time=time,
                    nPrice=nPrice,
                    nQty=nQty,
                    commission=commission,
                    is_long=is_long,
                    nMargin=nMargin,
                )

        elif is_new and ((is_buy and is_long) or (is_sell and is_short)):
            lockBalance, balance = nMargin, 0

        elif is_canceled and ((is_buy and is_long) or (is_sell and is_short)):
            lockBalance, balance = -nMargin, 0

        return lockBalance, balance

    def open_position(
        self,
        position: str,
        time: str,
        nPrice: int,
        nQty: int,
        commission: int,
        nMargin: int,
    ) -> tuple[int, int]:
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
        self.openPositions[position]["entryNprice"] = self.p_weight // self.weight

        return nMargin, 0

    def close_position(
        self,
        oid: int,
        position: str,
        time: str,
        nPrice: int,
        nQty: int,
        commission: int,
        is_long: bool,
        nMargin: int,
    ) -> tuple[int, int]:
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
        side, _ = ("TakeProfits", 1) if (nPnl > 0) else ("StopLosses", -1)
        pnl: float = nPnl / self.con.scale
        roi = self.con.to_nRoi(nPnl, nMargin) / self.con.scale

        self.openPositions[position]["realizedPNL"] += pnl
        self.openPositions[position]["realizedROI"] += roi
        self.openPositions[position]["tempNqty"] -= nQty

        self.openPositions[position][side] = {
            oid: {
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
            self.closePositions[oid] = {
                "positionSide": temp["positionSide"],
                "openTime": temp["openTime"],
                "closeTime": time,
                "entryPrice": self.con.to_price(eNprice),
                "closePrice": price,
                "quantity": self.con.to_qty(temp["nQuantity"]),
                "nominalQty": self.con.to_qty(temp["nominalNqty"]),
                "nominalCommission": self.con.to_qty(temp["nominalNcommission"]),
                "laverage": temp["laverage"],
                "realizedPNL": temp["realizedPNL"],
                "realizedROI": temp["realizedROI"],
                "TakeProfits": temp["TakeProfits"],
                "StopLosses": temp["StopLosses"],
            }
        return -nMargin, nPnl
