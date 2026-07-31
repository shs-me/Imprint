"""Live Binance Futures WebSocket connection worker."""

import asyncio
from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from .....utils.handlers import supervisor
from .....utils.monitoring.agent_manager import AgentManager
from ....base.base_wss import Wss


class GetUserDataWSSAgent(Wss):
    """Asynchronous WebSocket client streaming live aggTrades into DataStream ring buffer."""

    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager=manager)

        self.execution_event: Event = execution_event

        self.user_data_uri: str = manager.cfgConnector.get_user_data_uri_for_wss

    async def run_wss__engine(self) -> None:
        """Asynchronous event loop managing WebSocket connection and pushing raw JSON bytes to DataStream."""

        # Local Links
        execution_event = self.execution_event
        proc_status, task_status = self.proc_status, self.task_status
        wid, rid = self.gus_wid, self.gus_rid
        data, data_size = self.gus_data, self.gus_data_size
        data_header = self.gus_data_header
        cell_amount, safe_lag = self.gus_cell_amount, self.gus_safe_lag
        set_raw_data, alarm_clock = self.set_raw_data, self.alarm_clock
        # - - -
        while True:
            # - - -
            async with connect(self.user_data_uri, ping_interval=20) as ws:
                while True:
                    if proc_status[0] != 0 or task_status[0] != 0:
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
                        if execution_event.is_set() is False:
                            execution_event.set()

    async def extend_listen_key(self) -> None:
        while True:
            pass


@supervisor()
def run_get_user_data_wss(execution_event: Event, **kwargs) -> None:
    """Supervisor-wrapped entry point launching live Wss process."""

    agent = GetUserDataWSSAgent(kwargs["manager"], execution_event=execution_event)
    asyncio.run(agent.run_wss__engine())
