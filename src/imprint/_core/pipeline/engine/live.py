import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from imprint._core.configs import RingBuf
from imprint._core.footprint import SyncWithExecution
from imprint._core.pipeline.engine.base import Base
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils import AggTradesDecoder


@dataclass(slots=True)
class SyncViaEvent(SyncWithExecution):
    execution_event: Event

    @override
    def sync_with_execution(self) -> None:
        if self.execution_event.is_set() is False:
            self.execution_event.set()


@dataclass(slots=True)
class Live(Base):
    engine_event: Event

    decoder: AggTradesDecoder[None] = field(init=False)
    gap_stream: RingBuf = field(init=False)
    have_gap: memoryview = field(init=False)
    gap_first_id: memoryview = field(init=False)
    gap_last_id: memoryview = field(init=False)

    wid_offset: int = field(default=0, init=False)
    pass_lag: int = field(default=0, init=False)
    pass_lag_limit: int = field(default=2, init=False)

    def __post_init__(self) -> None:
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

    @override
    def alarm_clock(self) -> None:
        self.engine_event.wait(0.1)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        if self.gap_stream.wid_buf[0] != self.gap_stream.rid_buf[0]:
            trades = self.decoder.decode(self.gap_stream.get_data())
            self.processing_trades(trades)

        trades = self.decoder.decode(raw_data[:])
        self.processing_trades(trades)

    def processing_trades(
        self, trades: Iterator[tuple[float, float, int, int, int]] | None
    ) -> None:
        if trades is None:
            self.manager.dump_exc()
            return self.manager.set_proc_sc(
                scs.DECODE_ERROR, wait_main_task=True
            )

        for p, q, t, m, a in trades:
            if not self.gap_first_id[0]:
                self.gap_first_id[0] = a - 1

            diff = a - self.gap_first_id[0]
            if diff == 1:
                self.gap_first_id[0] = a
                self.set_data(p, q, t, m, a)
                nid = self.at_wid + self.wid_offset + 1
                self.at_wid: int = nid if (nid < self.at_max_row) else 0

            elif diff > 1:
                self.gap_last_id[0] = max(self.gap_last_id[0], a)
                if not self.have_gap[0]:
                    self.have_gap[0] = 1

                self.wid_offset = max(self.wid_offset, diff)
                self.set_data(p, q, t, m, a)

    def set_data(self, p: float, q: float, t: int, m: int, a: int) -> None:
        con = self.algorithm._engine.fp.con
        # - - -
        nid: int = (a - self.gap_first_id[0]) + self.at_wid
        row: int = nid if (nid < self.at_max_row) else (nid - self.at_max_row)

        self.agg_trades[row, 0] = round(p * con.price_mult)
        self.agg_trades[row, 1] = round(q * con.qty_mult)
        self.agg_trades[row, 2] = t
        self.agg_trades[row, 3] = m

    @override
    def post_update(self) -> None:
        if self.algorithm._sync.lag_is_safe() is False:
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.manager.set_proc_sc(
                    scs.ANALYSIS_LAG_MORE_SAFE_LAG, wait_main_task=False
                )

        if self.engine_event.is_set():
            self.engine_event.clear()

    @override
    def post_final_action(self) -> None:
        self.algorithm._sync.sync_with_execution()
