import asyncio
from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from ....constant import WS_STREAMS_PROD_URL
from ....utils.handlers import error_handler
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_wss import Wss


class WssAgent(Wss):
    def __init__(self, manager: AgentManager, wake_up_parser: Event) -> None:
        super().__init__(manager=manager)

        self.wake_up_parser: Event = wake_up_parser

        self.symbol: str = manager.cfgCoin.symbol
        self.wss_aggTrades_url: str = (
            f"{WS_STREAMS_PROD_URL}/ws/{self.symbol.lower()}@aggTrade"
        )

    @error_handler(set_status_code=True)
    async def run_wss_engine(self) -> None:
        # Local Links
        wake_up_parser = self.wake_up_parser
        proc_status, task_status = self.proc_status, self.task_status
        wCellC = self.wCellC
        data, data_size = self.data, self.data_size
        data_header = self.data_header
        cell_amount = self.cell_amount
        set_raw_data = self.set_raw_data
        # - - -
        while True:
            # - - -
            async with connect(self.wss_aggTrades_url, ping_interval=20) as ws:
                while True:
                    if proc_status[0] != 0 or task_status[0] != 0:
                        task: bool | int = self.check_base_task(complete=True)
                        if isinstance(task, bool):
                            if task:
                                return
                    
                    raw_data = await ws.recv(decode=False)
                    if set_raw_data(
                        raw_data=raw_data,
                        data=data,
                        data_header=data_header,
                        wCellC=wCellC,
                        cell_amount=cell_amount,
                        data_size=data_size,
                    ):
                        if wake_up_parser.is_set() is False:
                            wake_up_parser.set()


@manager_office()
def run_wss(parsing_event: Event, **kwargs) -> None:
    agent = WssAgent(kwargs["manager"], wake_up_parser=parsing_event)
    asyncio.run(agent.run_wss_engine())
