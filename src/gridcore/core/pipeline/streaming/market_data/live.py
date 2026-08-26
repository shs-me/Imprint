from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from ....ipc import NodeManager
from ..base import Base, scs


class Live(Base):
    def __init__(self, manager: NodeManager, engine_event: Event) -> None:
        super().__init__(manager=manager)

        self.engine_event: Event = engine_event

        self.agg_trades_uri: str = manager.cfgConnector.market_data_uri_for_wss

    async def run_wss__engine(self) -> None:
        # Local Links
        engine_event = self.engine_event
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
                        task: int = self.check_base_task()
                        if task & scs.EXIT:
                            return self.set_proc_sc(scs.EXIT, wait_main_task=False)

                        if task & scs.COMPLETE:
                            self.final_actions()
                            return self.set_proc_sc(scs.COMPLETE, wait_main_task=False)

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
                        if engine_event.is_set() is False:
                            engine_event.set()
