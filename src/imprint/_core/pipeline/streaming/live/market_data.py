import asyncio
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import final, override

from websockets import ClientConnection

from imprint._core.configs import MarketDataGapStream
from imprint._core.pipeline.streaming.live.base import Base
from imprint._core.settings import StatusCodes as scs


@final
@dataclass(slots=True)
class MarketData(Base):
    """Streaming market data processor managing order book updates and gap recovery.

    Parameters
    ----------
    engine_event : Event
        Multiprocessing synchronization event signaled when new data is written
        to the ring buffer.

    Attributes
    ----------
    have_gap : memoryview
        Single-element shared memory boolean flag indicating whether a sequence
        gap has been detected.
    first_gap_id : memoryview
        Single-element shared memory 64-bit integer specifying the starting trade
        ID of the missing sequence.
    last_gap_id : memoryview
        Single-element shared memory 64-bit integer specifying the ending trade
        ID of the missing sequence.
    gap_task : asyncio.Task[None] | None
        Background asynchronous task responsible for monitoring and recovering
        sequence gaps.
    sem : asyncio.Semaphore
        Concurrency limiter restricting simultaneous REST gap recovery requests
        to a maximum of 5.
    """

    engine_event: Event

    mdgs: MarketDataGapStream = field(init=False)
    have_gap: memoryview = field(init=False)
    first_gap_id: memoryview = field(init=False)
    last_gap_id: memoryview = field(init=False)

    sem: asyncio.Semaphore | None = field(default=None, init=False)
    gap_task: asyncio.Task[None] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize shared memory views and base configuration."""
        self.mdgs = self.manager.cfgMarketDataGapStream
        self.have_gap = self.mdgs.have_gap.view
        self.first_gap_id = self.mdgs.gap_first_id.view.cast("q")
        self.last_gap_id = self.mdgs.gap_last_id.view.cast("q")

    @override
    async def on_pre_connect(self) -> None:
        """Spawn the gap monitoring background task prior to establishing connection."""
        if self.gap_task is None:
            self.gap_task = asyncio.create_task(self.monitor_gap())

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        """Receive incoming WebSocket frames and write them to the shared ring buffer.

        Parameters
        ----------
        ws : ClientConnection
            Active WebSocket connection instance.

        Raises
        ------
        RuntimeError
            Terminates process status code if raw data size exceeds the buffer limit.
        """
        _ = self.manager.cfgMarketDataStream.ring_buf
        # - - -
        raw_data: bytes = await ws.recv(decode=False)

        while _.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < _.data_size:
            _.set_data(raw_data)
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )

        if not self.engine_event.is_set():
            self.engine_event.set()

    async def monitor_gap(self) -> None:
        """Monitor shared memory for sequence gaps and fetch missing trades via REST."""
        wid, rid = self.mdgs.ring_buf.wid_buf, self.mdgs.ring_buf.rid_buf
        #  - - -
        try:
            if self.sem is None:
                self.sem = asyncio.Semaphore(5)

            while True:
                try:
                    while not self.have_gap[0]:
                        await asyncio.sleep(0.01)

                    while wid[0] != rid[0]:
                        await asyncio.sleep(0.01)

                    first_id: int = self.first_gap_id[0]
                    last_gap_id: int = self.last_gap_id[0]

                    if (last_gap_id - first_id) <= 1000:
                        await self.gap_request(first_id, last_gap_id, self.sem)
                    else:
                        async with asyncio.TaskGroup() as tg:
                            curr_first = first_id
                            while curr_first < last_gap_id:
                                curr_last = min(curr_first + 1000, last_gap_id)
                                tg.create_task(
                                    self.gap_request(
                                        curr_first, curr_last, self.sem
                                    )
                                )
                                curr_first = curr_last

                    self.have_gap[0] = 0

                finally:
                    ...

        except Exception as e:
            self.manager.dump_exc(True)
            self.manager.set_log(f"{self.stream} Gap request failed: {e}")
        finally:
            self.gap_task = None

    async def gap_request(
        self, first_id: int, last_id: int, sem: asyncio.Semaphore
    ) -> None:
        """Fetch missing aggregate trades within a trade ID range and populate the ring buffer.

        Parameters
        ----------
        first_id : int
            Starting trade identifier of the gap range (inclusive).
        last_id : int
            Ending trade identifier of the gap range (inclusive).
        sem : asyncio.Semaphore
            Concurrency semaphore to rate-limit REST requests.

        Raises
        ------
        RuntimeError
            Terminates process status code if fetched raw data exceeds buffer size.
        """
        _ = self.mdgs.ring_buf
        # - - -
        async with sem:
            raw_data: bytes = await self.rest.get_agg_trades(first_id, last_id)

        while _.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < _.data_size:
            _.set_data(raw_data)
            if not self.engine_event.is_set():
                self.engine_event.set()
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )
