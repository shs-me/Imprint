import struct
import time

from .... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_footprint_writer import FootprintWriter
from ...base.base_parsing import Parsing


class FootprintWriterV2(FootprintWriter):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)
        self.execution_sim: bool = self.manager.cfgBacktesting.execution_sim

    def update(self, price: float, qty: float, timestamp: int, is_sell: bool) -> bool:
        nPrice: int = self.con.to_nPrice(price)
        idy: int | None = self.con.to_idy(nPrice=nPrice)
        idx: int | None = self.con.to_idx(timestamp=timestamp, is_sell=is_sell)
        if idx is not None:
            if idy is not None:
                self.last_idx[0] = idx
                if self.execution_sim:
                    if self.update_dfm(nPrice, timestamp) is False:
                        return False

                self.update_footprint_and_headers_and_indicators_and_coords(
                    price=price,
                    qty=qty,
                    timestamp=timestamp,
                    is_sell=is_sell,
                    nPrice=nPrice,
                    idy=idy,
                    idx=idx,
                )
            else:
                self.set_proc_sc(code=scs.FP_IDY_FILLED)
        else:
            self.wait_read_space()
            self.set_proc_sc(code=scs.FP_IDX_FILLED)

        self.counterTicks[0] += 1
        return self.copy_to()

    def update_dfm(self, nPrice: int, timestamp: int) -> bool:
        buf: int = self.space_flag[0]
        dfm, dfm_rid = (
            (self.dfm_1, self.dfm_1RID) if (buf == 0) else (self.dfm_2, self.dfm_2RID)
        )
        rid: int = dfm_rid[0]
        if rid > 0:
            pre_rid: int = rid - 1
            if dfm[pre_rid, c.DFM_nPrice] == nPrice:
                dfm[pre_rid, c.DFM_endTimestamp] = timestamp
                return True

        dfm[rid, c.DFM_nPrice] = nPrice
        dfm[rid, c.DFM_startTimestamp] = timestamp
        dfm[rid, c.DFM_endTimestamp] = timestamp

        new_rid: int = rid + 1
        if new_rid >= self.dfmLines:
            self.set_proc_sc(scs.BUF_DFM_FILLED)
            return False
        else:
            dfm_rid[0] = new_rid
            return True


class ParsingAgent(Parsing):
    def __init__(self, manager: AgentManager, writer: FootprintWriter) -> None:
        super().__init__(manager=manager, writer=writer)

    def alarm_clock(self) -> None:
        while self.wCellC[0] == self.rCellC[0]:
            time.sleep(0)

    def set_trade_data(self, raw_data: memoryview) -> None:
        self.price[0], self.qty[0], self.timestamp[0], self.is_sell = struct.unpack(
            "@ddq?", raw_data
        )

    def update_success(self) -> None:
        return super().update_success()

    def post_update(self) -> None:
        return super().post_update()

    def post_final_action(self) -> None:
        print(f"Count Prepped Ticks: {self.writer.counterTicks[0]}", flush=True)


@manager_office()
def run_parsing_sim(**kwargs) -> None:
    writer = FootprintWriterV2(kwargs["manager"])
    agent = ParsingAgent(kwargs["manager"], writer=writer)
    agent.run_parsing_engine()
