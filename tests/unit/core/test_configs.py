"""Unit tests for `imprint.core.configs`."""

import pytest

from imprint._core.configs import (
    FLOAT64,
    INT64,
    OFFSET,
    PERCENT,
    UBYTE,
    Account,
    Coin,
    Connector,
    DataStream,
    Footprint,
    GetUserStream,
    Metrics,
    RiskManagement,
    Segment,
    Setup,
    SetUserStream,
    Signal,
    TextStream,
    pct,
)
from imprint._core.settings import Timeframe


class TestModuleConstants:
    def test_byte_and_size_constants(self) -> None:
        assert PERCENT == 10_000
        assert OFFSET == 0
        assert UBYTE == 1
        assert INT64 == 8
        assert FLOAT64 == 8


class TestSegment:
    def test_segment_initialization(self) -> None:
        seg = Segment(size=64)
        assert seg.size == 64
        assert seg.offset is None
        assert seg.view is None


class Testpct:
    @pytest.mark.parametrize(
        "str_,expected_int",
        [
            ("0.05%", 5),
            ("0.02%", 2),
            ("1%", 100),
            ("10%", 1_000),
            ("100%", 10_000),
            ("50%", 5_000),
            ("0%", 0),
        ],
    )
    def test_string_percent_converts_to_fixed_point_int(
        self, str_: str, expected_int: int
    ) -> None:
        assert pct(str_).fixed == expected_int


class TestAccount:
    def test_defaults(self) -> None:
        account = Account()
        assert account.leverage == 20
        assert account.balance == 100.0
        assert account.min_order_size == 5.0
        assert account.save_orders_history is False
        assert account.latency_ms == 100
        assert account.active_order_limit == 1000
        assert account.scale_mult == 10**15

    def test_scale_mult_derived_from_scale_prec(self) -> None:
        assert Account(scale_prec=15).scale_mult == 10**15
        assert Account(scale_prec=8).scale_mult == 10**8
        assert Account(scale_prec=0).scale_mult == 1

    def test_commission_and_slippage_are_percent_instances(self) -> None:
        account = Account(
            taker_commission=pct("0.05%"),
            maker_commission=pct("0.02%"),
            slippage=pct("0.1%"),
        )
        assert account.taker_commission.fixed == 5
        assert account.maker_commission.fixed == 2
        assert account.slippage.fixed == 10


class TestRiskManagement:
    def test_defaults_produce_expected_fixed_point_values(self) -> None:
        risk = RiskManagement()
        assert risk.max_lock_balance.fixed == 1_000
        assert risk.max_loss_balance.fixed == 1_000
        assert risk.entry_qty.fixed == 100
        assert risk.tp_dev.fixed == 500
        assert risk.sl_dev.fixed == 500
        assert risk.pass_signal_if_analysis_time_big == 50_000
        assert risk.pass_execute_signal_if_timer_ms_exepired == 1_000

    def test_custom_percent_overrides(self) -> None:
        risk = RiskManagement(
            entry_qty=pct("0.5%"),
            tp_dev=pct("2%"),
            sl_dev=pct("1.8%"),
            pass_signal_if_analysis_time_big=10_000,
            pass_execute_signal_if_timer_ms_exepired=500,
        )
        assert risk.entry_qty.fixed == 50
        assert risk.tp_dev.fixed == 200
        assert risk.sl_dev.fixed == 180
        assert risk.pass_signal_if_analysis_time_big == 10_000
        assert risk.pass_execute_signal_if_timer_ms_exepired == 500


class TestCoin:
    def test_defaults(self) -> None:
        coin = Coin()
        assert coin.symbol == "DASHUSDT"
        assert coin.tick_size == "0.01"
        assert coin.lot_size == "0.001"

    @pytest.mark.parametrize(
        "tick_size,expected_prec,expected_mult",
        [
            ("0.01", 2, 100),
            ("0.001", 3, 1_000),
            ("1", 0, 1),
            ("0.1", 1, 10),
        ],
    )
    def test_price_precision_and_multiplier(
        self, tick_size: str, expected_prec: int, expected_mult: int
    ) -> None:
        coin = Coin(tick_size=tick_size)
        assert coin.price_prec == expected_prec
        assert coin.price_mult == expected_mult

    @pytest.mark.parametrize(
        "lot_size,expected_prec,expected_mult",
        [
            ("0.001", 3, 1_000),
            ("0.1", 1, 10),
            ("1", 0, 1),
        ],
    )
    def test_qty_precision_and_multiplier(
        self, lot_size: str, expected_prec: int, expected_mult: int
    ) -> None:
        coin = Coin(lot_size=lot_size)
        assert coin.qty_prec == expected_prec
        assert coin.qty_mult == expected_mult


class TestFootprint:
    def test_default_bar_count_for_h1_one_day(self) -> None:
        fp = Footprint(timeframe=Timeframe.H1, chart_range=1)
        assert fp.bar_count == 24
        assert fp.fp_cols == 48
        assert fp.fp_panel_cols == 50
        assert fp.save_fp_headers is False
        assert fp.fp_rows == 10001

    def test_bar_count_for_m5_one_day(self) -> None:
        fp = Footprint(timeframe=Timeframe.M5, chart_range=1)
        assert fp.bar_count == 288
        assert fp.fp_cols == 576
        assert fp.fp_panel_cols == 578

    def test_chart_range_zero_is_treated_as_one_day(self) -> None:
        fp_zero = Footprint(timeframe=Timeframe.M5, chart_range=0)
        fp_one = Footprint(timeframe=Timeframe.M5, chart_range=1)
        assert fp_zero.bar_count == fp_one.bar_count

    def test_chart_range_scales_bar_count_linearly(self) -> None:
        fp = Footprint(timeframe=Timeframe.M5, chart_range=7)
        assert fp.bar_count == (7 * 86_400_000) // 300_000

    def test_col_indices_are_fixed(self) -> None:
        fp = Footprint()
        assert fp.colVP == -2
        assert fp.colDP == -1

    def test_get_bar_count_when_interval_greater_or_equal_to_day_ms(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force ivlMs >= dayMs to cover branch: (ivlMs // dayMs)
        fp = Footprint(timeframe=Timeframe.H1, chart_range=1)
        monkeypatch.setattr(fp, "timeframe", 100_000_000)
        assert fp._get_bar_count(day=1) == 100_000_000 // 86_400_000


class TestSetup:
    def test_defaults(self) -> None:
        setup = Setup()
        assert setup.backtesting is True
        assert setup.execution is True
        assert setup.backtest_start_date == "2026-01-01"
        assert setup.backtest_end_date == "2026-01-01"
        assert setup.algorithm_module == ""
        assert setup.algorithm_class_name == ""
        assert setup.execution_module == ""
        assert setup.execution_class_name == ""
        assert setup.agg_trades_decoder_module == ""
        assert setup.agg_trades_decoder_class_name == ""
        assert setup.user_stream_decoder_module == ""
        assert setup.user_stream_decoder_class_name == ""
        assert setup.order_encoder_module == ""
        assert setup.order_encoder_class_name == ""


class TestConnector:
    def test_defaults_are_empty_strings(self) -> None:
        connector = Connector()
        assert connector.base_uri_for_rest == ""
        assert connector.base_uri_for_ws == ""
        assert connector.base_uri_for_wss == ""
        assert connector.market_data_uri_for_wss == ""
        assert connector.get_user_data_uri_for_wss == ""
        assert connector.set_user_data_uri_for_wss == ""

    def test_custom_uris_are_kept_verbatim(self) -> None:
        connector = Connector(
            base_uri_for_rest="https://fapi.binance.com",
            base_uri_for_ws="wss://ws-fapi.binance.com",
            base_uri_for_wss="wss://fstream.binance.com",
            market_data_uri_for_wss="wss://fstream.binance.com/stream",
            get_user_data_uri_for_wss="wss://fstream.binance.com/user",
            set_user_data_uri_for_wss="wss://ws-fapi.binance.com/order",
        )
        assert connector.base_uri_for_rest == "https://fapi.binance.com"
        assert connector.base_uri_for_ws == "wss://ws-fapi.binance.com"
        assert connector.base_uri_for_wss == "wss://fstream.binance.com"
        assert (
            connector.market_data_uri_for_wss
            == "wss://fstream.binance.com/stream"
        )
        assert (
            connector.get_user_data_uri_for_wss
            == "wss://fstream.binance.com/user"
        )
        assert (
            connector.set_user_data_uri_for_wss
            == "wss://ws-fapi.binance.com/order"
        )


class TestSharedMemorySegmentsAndMetrics:
    def test_metrics_segments_offsets_and_page_alignment(self) -> None:
        metrics = Metrics(count_procs=4)
        assert metrics.procs_status.size == (4 * 2) * INT64
        assert metrics.main_status.size == 4 * INT64
        assert metrics.time_start_reading.size == INT64
        assert metrics.trade_read_time.size == INT64
        assert metrics.engine_complete.size == UBYTE

        # Verify 4096-byte page alignment
        assert metrics.shm_size % 4096 == 0
        assert metrics.shm_size >= metrics.engine_complete.offset[1]

        # Verify contiguous monotonic offsets
        assert metrics.procs_status.offset[0] == 0
        assert metrics.procs_status.offset[1] == metrics.main_status.offset[0]
        assert (
            metrics.main_status.offset[1]
            == metrics.time_start_reading.offset[0]
        )
        assert (
            metrics.time_start_reading.offset[1]
            == metrics.trade_read_time.offset[0]
        )
        assert (
            metrics.trade_read_time.offset[1]
            == metrics.engine_complete.offset[0]
        )


class TestRingBuffers:
    def test_text_stream_ring_buffer(self) -> None:
        ts = TextStream()
        assert ts.data_size == 1024
        assert ts.data_header_size == 8
        assert ts.cell_amount == 100
        assert ts.count_reader == 10
        assert ts.count_writer == 10
        assert ts.safe_lag == int(100 * 0.9)
        assert ts.shm_size % 4096 == 0
        assert ts.data.size == 10 * (100 * 1024)

    def test_signal_ring_buffer(self) -> None:
        sig = Signal()
        assert sig.data_size == 32
        assert sig.data_header_size == 1
        assert sig.cell_amount == 1000
        assert sig.safe_lag == int(1000 * 0.9)
        assert sig.shm_size % 4096 == 0

    def test_get_user_stream_ring_buffer(self) -> None:
        gus = GetUserStream()
        assert gus.data_size == 128
        assert gus.data_header_size == 1
        assert gus.cell_amount == 1000
        assert gus.safe_lag == int(1000 * 0.9)
        assert gus.shm_size % 4096 == 0

    def test_set_user_stream_ring_buffer(self) -> None:
        sus = SetUserStream()
        assert sus.data_size == 128
        assert sus.data_header_size == 1
        assert sus.cell_amount == 1000
        assert sus.safe_lag == int(1000 * 0.9)
        assert sus.shm_size % 4096 == 0

    def test_data_stream_ring_buffer(self) -> None:
        ds = DataStream()
        assert ds.data_size == 256
        assert ds.data_header_size == 1
        assert ds.cell_amount == 10_000
        assert ds.safe_lag == int(10_000 * 0.9)
        assert ds.shm_size % 4096 == 0
