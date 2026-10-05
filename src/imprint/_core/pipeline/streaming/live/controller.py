import asyncio
import importlib
from asyncio import Task
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event, Semaphore
from typing import final

from imprint._core.ipc.manager import NodeManager
from imprint._core.pipeline.streaming.live.market_data import MarketData
from imprint._core.pipeline.streaming.live.order import Order
from imprint._core.pipeline.streaming.live.user_data import UserData
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils.base_adapters import ExchangeREST


@final
@dataclass(slots=True)
class Controller:
    """Supervises and manages live streaming pipeline components and their lifecycle.

    Coordinates the market data stream, user data stream, order execution stream,
    and REST client interactions based on process signals and configuration setups.

    Parameters
    ----------
    manager : NodeManager
        Process-level node manager coordinating inter-process communication and state.
    engine_event : Event
        Multiprocessing event signaling engine state transitions to market data stream.
    execution_event : Event
        Multiprocessing event signaling execution readiness to user data stream.
    wss_sem : Semaphore
        Multiprocessing semaphore controlling WebSocket send rate or concurrency.

    Attributes
    ----------
    market_data_stream : MarketData
        Stream handler consuming public market data feeds.
    user_data_stream : UserData
        Stream handler consuming authenticated user account and execution events.
    order_stream : Order
        Stream handler transmitting order payloads to the exchange.
    rest : ExchangeREST
        REST client instance initialized for exchange-specific HTTP requests.
    """

    manager: NodeManager
    engine_event: Event
    execution_event: Event
    wss_sem: Semaphore

    market_data_stream: MarketData = field(init=False)
    user_data_stream: UserData = field(init=False)
    order_stream: Order = field(init=False)

    rest: ExchangeREST = field(init=False)

    def __post_init__(self) -> None:
        """Initialize streaming modules, REST client, and configuration bindings."""
        m_name: str = self.manager.cfgSetup.exchange_rest_module
        c_name: str = self.manager.cfgSetup.exchange_rest_class_name
        rest_type: type[ExchangeREST] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_log(
            f"{rest_type.__name__} used as {ExchangeREST.__name__}"
        )

        cfgConnector = self.manager.cfgConnector
        self.rest = rest_type(
            logger=self.manager.set_log,
            symbol=self.manager.cfgCoin.symbol,
        )
        self.rest.base_url = cfgConnector.base_rest_url

        uri = cfgConnector.market_data_stream_url
        self.market_data_stream = MarketData(
            self.manager, self.rest, uri, self.engine_event
        )
        uri = cfgConnector.user_data_stream_url
        self.user_data_stream = UserData(
            self.manager, self.rest, uri, self.execution_event
        )
        uri = cfgConnector.order_stream_url
        self.order_stream = Order(self.manager, self.rest, uri, self.wss_sem)

    async def run_supervisor(self, streams: list[Task[None]]) -> None:
        """Monitor active stream tasks and process control exit or completion signals.

        Parameters
        ----------
        streams : list[Task[None]]
            Active asynchronous tasks corresponding to running data streams.
        """
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(
                        scs.EXIT, wait_main_task=False
                    )

                if task & scs.COMPLETE:
                    self.market_data_stream.final_actions()
                    return self.manager.set_proc_sc(
                        scs.COMPLETE, wait_main_task=False
                    )

            for stream in streams:
                if stream.done():
                    return

            await asyncio.sleep(0.1)

    async def run_streams(self) -> None:
        """Execute concurrent data streams and supervise their lifecycle within a TaskGroup."""
        async with asyncio.TaskGroup() as tg:
            streams: list[Task[None]] = [
                tg.create_task(self.market_data_stream.run())
            ]
            if self.manager.cfgSetup.execution:
                streams.append(tg.create_task(self.user_data_stream.run()))
                streams.append(tg.create_task(self.order_stream.run()))

            supervisor: Task[None] = tg.create_task(
                self.run_supervisor(streams)
            )
            await supervisor
