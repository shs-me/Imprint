"""Live Binance Futures WebSocket connection worker."""

import asyncio
from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from .....settings import DataStreamProc
from .....utils.handlers import supervisor
from .....utils.monitoring.agent_manager import AgentManager
from ....base.base_wss import Wss


class MarketDataWSSAgent(Wss):
    """Asynchronous WebSocket client streaming live aggTrades into DataStream ring buffer."""

    def __init__(self, manager: AgentManager, parsing_event: Event) -> None:
        super().__init__(manager=manager)

        self.parsing_event: Event = parsing_event

        self.agg_trades_uri: str = manager.cfgConnector.market_data_uri_for_wss

    async def run_wss__engine(self) -> None:
        """Asynchronous event loop managing WebSocket connection and pushing raw JSON bytes to DataStream."""

        # Local Links
        parsing_event = self.parsing_event
        have_status, task_status = self.have_status, self.task_status
        wid, rid = self.ds_wid, self.ds_rid
        data, data_size = self.ds_data, self.ds_data_size
        data_header = self.ds_data_header
        cell_amount, safe_lag = self.ds_cell_amount, self.ds_safe_lag
        set_raw_data, alarm_clock = self.set_raw_data, self.alarm_clock
        # - - -
        while True:
            # - - -
            async with connect(self.agg_trades_uri, ping_interval=20) as ws:
                while True:
                    if have_status():
                        task: bool | int = self.check_base_task(complete=True)
                        if isinstance(task, bool):
                            if task:
                                return

                    raw_data = await ws.recv(decode=False)
                    alarm_clock(wid, rid, cell_amount, safe_lag)
                    if set_raw_data(
                        raw_data=raw_data,
                        writer_id=wid,
                        data=data,
                        data_header=data_header,
                        data_size=data_size,
                        cell_amount=cell_amount,
                    ):
                        if parsing_event.is_set() is False:
                            parsing_event.set()


@supervisor()
def run_market_data_wss(
    parsing_event: Event, proc: DataStreamProc = DataStreamProc(), **kwargs
) -> None:
    """Supervisor-wrapped entry point launching live Wss process."""

    agent = MarketDataWSSAgent(kwargs["manager"], parsing_event=parsing_event)
    asyncio.run(agent.run_wss__engine())
