import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import final, override

import numpy as np
from numpy.typing import NDArray

from imprint._core.configs import RingBuf
from imprint._core.footprint import SyncWithExecution
from imprint._core.pipeline.engine.base import Base
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils import AggTradesDecoder


@dataclass(slots=True)
class SyncViaEvent(SyncWithExecution):
    """Synchronization mechanism via multiprocessing Event for live execution.

    Parameters
    ----------
    execution_event : Event
        Multiprocessing event flag signaling execution coordination.

    Attributes
    ----------
    execution_event : Event
        Multiprocessing event flag signaling execution coordination.
    """

    execution_event: Event

    @override
    def sync_with_execution(self) -> None:
        """Set the execution event if not already set."""
        if not self.execution_event.is_set():
            self.execution_event.set()


@final
@dataclass(slots=True)
class Live(Base):  # pyright: ignore[reportUninitializedInstanceVariable]
    """Live execution engine processing real-time market data streams and handling gaps.

    Parameters
    ----------
    manager : NodeManager
        Inter-process communication and configuration manager for the engine node.
    algorithm : StrategyEngine
        Active strategy container holding the footprint engine and synchronization state.
    engine_event : Event
        Multiprocessing event signaling engine state updates.

    Attributes
    ----------
    engine_event : Event
        Multiprocessing event signaling engine state updates.
    decoder : AggTradesDecoder[None]
        Decoder instance for parsing raw aggregated trades payloads.
    gap_stream : RingBuf
        Ring buffer for receiving gap data streams.
    have_gap : memoryview
        Shared memory view indicating whether a data gap is active.
    gap_first_id : memoryview
        Shared memory view storing the starting identifier of a data gap.
    gap_last_id : memoryview
        Shared memory view storing the ending identifier of a data gap.
    head_id : int
        Current head trade identifier in sequence tracking.
    mid_id : int
        Intermediate trade identifier bridging trade sequences.
    tail_id : int
        Current tail trade identifier in sequence tracking.
    filled : ndarray of shape (N,)
        Boolean array tracking processed trade rows in the buffer.
    mask : int
        Bitmask computed from maximum row count for fast modulo indexing.
    pass_lag : int
        Counter for consecutive analysis lag occurrences.
    pass_lag_limit : int, default=2
        Threshold limit for consecutive lagged iterations before triggering status code.
    """

    engine_event: Event

    decoder: AggTradesDecoder[None] = field(init=False)
    gap_stream: RingBuf = field(init=False)
    have_gap: memoryview = field(init=False)
    gap_first_id: memoryview = field(init=False)
    gap_last_id: memoryview = field(init=False)

    head_id: int = field(default=0, init=False)
    mid_id: int = field(default=0, init=False)
    tail_id: int = field(default=0, init=False)

    filled: NDArray[np.bool_] = field(init=False)
    mask: int = field(init=False)

    pass_lag: int = field(default=0, init=False)
    pass_lag_limit: int = field(default=2, init=False)

    @override
    def __post_init__(self) -> None:
        """Initialize decoders, gap stream buffers, and tracking masks."""
        Base.__post_init__(self)

        m_name: str = self.manager.cfgSetup.agg_trades_decoder_module
        c_name: str = self.manager.cfgSetup.agg_trades_decoder_class_name
        decoder_type: type[AggTradesDecoder[None]] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_log(
            f"{decoder_type.__name__} used as {AggTradesDecoder.__name__}"
        )
        self.decoder = decoder_type()

        mdgs = self.manager.cfgMarketDataGapStream
        self.gap_stream = mdgs.ring_buf
        self.have_gap = mdgs.have_gap.view
        self.gap_first_id = mdgs.gap_first_id.view.cast("q")
        self.gap_last_id = mdgs.gap_last_id.view.cast("q")

        self.mask = self.at_max_row - 1
        self.filled = np.zeros(self.at_max_row, dtype=np.bool_)

    @override
    def alarm_clock(self) -> None:
        """Check gap stream, request missing data gaps, and wait for engine event signal."""
        self.check_gap_stream()
        self.gap_request()
        self.engine_event.wait(0.1)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        """Decode raw trade data, process trade sequence, and check gap streams.

        Parameters
        ----------
        raw_data : memoryview
            Raw binary trade payload from the data stream ring buffer.
        """
        self.check_gap_stream()
        trades = self.decoder.decode(raw_data[:])
        self.processing_trades(trades)
        self.gap_request()

    def check_gap_stream(self) -> None:
        """Poll and process trade records from the market data gap stream buffer."""
        while self.gap_stream.wid_buf[0] != self.gap_stream.rid_buf[0]:
            trades = self.decoder.decode(self.gap_stream.get_data())
            self.processing_trades(trades)

    def gap_request(self) -> None:
        """Initiate a data gap request if unindexed trade gaps are identified."""
        if self.mid_id and not self.have_gap[0]:
            self.gap_first_id[0] = self.head_id
            self.gap_last_id[0] = self.mid_id
            self.have_gap[0] = 1

    def processing_trades(
        self, trades: Iterator[tuple[float, float, int, int, int]] | None
    ) -> None:
        """Process decoded trade records and populate ring buffer structures.

        Parameters
        ----------
        trades : Iterator[tuple[float, float, int, int, int]] | None
            Iterator yielding tuples of `(price, quantity, timestamp, maker_flag, aggregate_id)`,
            or None if decoding failed.
        """
        if trades is None:
            self.manager.dump_exc()
            return self.manager.set_proc_sc(
                scs.DECODE_ERROR, wait_main_task=True
            )

        mask = self.mask
        con = self.engine.fp.con

        for p, q, t, m, a in trades:
            if self.head_id == 0:
                self.head_id, self.tail_id = a, a
                self.at_rid, self.at_wid = a & mask, a & mask

            if a < self.head_id:
                continue

            if (a - self.head_id) >= self.at_max_row:
                return self.manager.set_proc_sc(
                    scs.BIG_GAP, wait_main_task=True
                )

            self.tail_id = max(self.tail_id, a)

            if (a > self.head_id) and (self.mid_id == 0):
                self.mid_id = a

            row = a & mask
            self.agg_trades[row, 0] = round(p * con.price_mult[0])
            self.agg_trades[row, 1] = round(q * con.qty_mult[0])
            self.agg_trades[row, 2] = t
            self.agg_trades[row, 3] = m
            self.filled[row] = True

            while (
                self.head_id <= self.tail_id
                and self.filled[self.head_id & mask]
            ):
                self.filled[self.head_id & mask] = False
                self.head_id += 1
                if self.mid_id and (self.head_id >= self.mid_id):
                    self.mid_id = 0

            if (self.mid_id == 0) and (self.head_id < self.tail_id):
                self.mid_id = self.tail_id

            self.at_wid = self.head_id & mask

    @override
    def post_update(self) -> None:
        """Monitor analysis lag tolerances and clear engine execution events."""
        if not self.strategy._sync.lag_is_safe():
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.manager.set_proc_sc(
                    scs.ANALYSIS_LAG_MORE_SAFE_LAG, wait_main_task=False
                )

        if self.engine_event.is_set():
            self.engine_event.clear()

    @override
    def post_final_action(self) -> None:
        """Synchronize execution state upon final engine completion."""
        self.strategy._sync.sync_with_execution()
