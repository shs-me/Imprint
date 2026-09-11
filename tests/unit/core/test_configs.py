"""Unit tests for imprint._core.configs module verifying exact memory layouts and logic."""

from typing import Any

from imprint._core import configs as cfg
from imprint._core.settings import Timeframe


def test_percent_calculation() -> None:
    """Verify manual fixed-point percent calculation."""
    percent = cfg.Percent(0.05)
    # Manual calculation: round(0.05 / 100 * 10000) = round(5.0) = 5
    expected_fixed: int = 5
    assert percent.fixed == expected_fixed, (
        f"Expected percent fixed value {expected_fixed}, got {percent.fixed}"
    )


def test_account_scale_mult() -> None:
    """Verify Account scale multiplier initialization."""
    account = cfg.Account(scale_prec=8)
    # Manual calculation: 10 ** 8 = 100000000
    expected_mult: int = 100_000_000
    assert account.scale_mult == expected_mult, (
        f"Expected scale multiplier {expected_mult}, got {account.scale_mult}"
    )


def test_coin_precisions_and_multipliers() -> None:
    """Verify Coin precision parsing and derived multiplier calculations."""
    coin = cfg.Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")

    # Manual calculations:
    # "0.01".split(".")[-1] -> "01" -> length 2 -> mult 10**2 = 100
    # "0.001".split(".")[-1] -> "001" -> length 3 -> mult 10**3 = 1000
    assert coin.price_prec == 2, f"Expected price_prec 2, got {coin.price_prec}"
    assert coin.qty_prec == 3, f"Expected qty_prec 3, got {coin.qty_prec}"
    assert coin.price_mult == 100, (
        f"Expected price_mult 100, got {coin.price_mult}"
    )
    assert coin.qty_mult == 1000, f"Expected qty_mult 1000, got {coin.qty_mult}"


def test_footprint_bar_count_and_columns() -> None:
    """Verify Footprint bar count and panel column calculations."""
    fp = cfg.Footprint(timeframe=Timeframe.H1, chart_range=1)

    # Manual calculations:
    # dayMs = 1 * 24 * 60 * 60 * 1000 = 86,400,000
    # ivlMs = Timeframe.H1 = 3,600,000
    # bar_count = 86_400_000 // 3_600_000 = 24
    # fp_cols = 24 * 2 = 48
    # fp_panel_cols = 48 + 2 = 50
    expected_bar_count: int = 24
    expected_fp_cols: int = 48
    expected_fp_panel_cols: int = 50

    assert fp.bar_count == expected_bar_count, (
        f"Expected bar_count {expected_bar_count}, got {fp.bar_count}"
    )
    assert fp.fp_cols == expected_fp_cols, (
        f"Expected fp_cols {expected_fp_cols}, got {fp.fp_cols}"
    )
    assert fp.fp_panel_cols == expected_fp_panel_cols, (
        f"Expected fp_panel_cols {expected_fp_panel_cols}, got {fp.fp_panel_cols}"
    )


def test_metrics_shared_memory_layout() -> None:
    """Verify Metrics segment size, offsets, and page-aligned total shared memory size."""
    metrics = cfg.Metrics(count_procs=10)

    # Manual calculations:
    # count_procs = 10, INT64 = 8, UBYTE = 1
    # procs_status size: (10 * 2) * 8 = 160 -> offset: (0, 160)
    # main_status size: 10 * 8 = 80        -> offset: (160, 240)
    # time_start_reading size: 8           -> offset: (240, 248)
    # trade_read_time size: 8              -> offset: (248, 256)
    # engine_complete size: 1               -> offset: (256, 257)
    # Unaligned total raw size = 257
    # Page alignment formula: ((257 // 4096) + 1) * 4096 = 4096

    assert metrics.procs_status.size == 160
    assert metrics.procs_status.offset == (0, 160)

    assert metrics.main_status.size == 80
    assert metrics.main_status.offset == (160, 240)

    assert metrics.time_start_reading.size == 8
    assert metrics.time_start_reading.offset == (240, 248)

    assert metrics.trade_read_time.size == 8
    assert metrics.trade_read_time.offset == (248, 256)

    assert metrics.engine_complete.size == 1
    assert metrics.engine_complete.offset == (256, 257)

    assert metrics.shm_size == 4096, (
        f"Expected shm_size 4096, got {metrics.shm_size}"
    )


def test_market_data_stream_shared_memory_layout() -> None:
    """Verify MarketDataStream inner RingBuf offsets and page alignment."""
    md_stream = cfg.MarketDataStream()
    ring_buf = md_stream.ring_buf

    # Default parameters for MarketDataStream:
    # data_size = 256, data_header_size = 1, cell_amount = 10000
    # count_reader = 2, count_writer = 1, INT64 = 8
    # safe_lag = int(10000 * 0.9) = 9000
    #
    # Segments & Sizes:
    # reader_id size: 2 * 8 = 16                       -> offset: (0, 16)
    # writer_id size: 1 * 8 = 8                        -> offset: (16, 24)
    # data size: 1 * (10000 * 256) = 2,560,000         -> offset: (24, 2560024)
    # data_header size: 1 * (10000 * 1) = 10,000       -> offset: (2560024, 2570024)
    #
    # Raw needed size = 2,570,024
    # Page alignment: ((2570024 // 4096) + 1) * 4096 = 628 * 4096 = 2,572,288

    assert ring_buf.safe_lag == 9000
    assert ring_buf.reader_id.offset == (0, 16)
    assert ring_buf.writer_id.offset == (16, 24)
    assert ring_buf.data.offset == (24, 2_560_024)
    assert ring_buf.data_header.offset == (2_560_024, 2_570_024)

    expected_shm_size: int = 2_572_288
    assert md_stream.shm_size == expected_shm_size, (
        f"Expected shm_size {expected_shm_size}, got {md_stream.shm_size}"
    )


def test_ring_buf_read_write_operations() -> None:
    """Verify RingBuf read, write, memoryview binding, and safe lag detection."""
    ring_buf = cfg.RingBuf(
        data_size=32,
        data_header_size=1,
        cell_amount=10,
        count_writer=1,
        count_reader=1,
        cast_to_int64=True,
    )

    # Allocate mock backing buffer based on segment total size
    # Layout sizes: reader_id (8), writer_id (8), data (320), data_header (10) -> total 346
    total_buf_size: int = (
        ring_buf.reader_id.size
        + ring_buf.writer_id.size
        + ring_buf.data.size
        + ring_buf.data_header.size
    )
    raw_buffer = bytearray(total_buf_size)
    shm_view = memoryview(raw_buffer)

    # Bind slices manually as Base manager does
    ring_buf.reader_id.view = shm_view[0:8]
    ring_buf.writer_id.view = shm_view[8:16]
    ring_buf.data.view = shm_view[16:336]
    ring_buf.data_header.view = shm_view[336:346]

    ring_buf.post_init()

    # Manual expectations after post_init:
    # cast_to_int64 is True -> data_size = 32 // 8 = 4 (measured in int64 elements)
    assert ring_buf.data_size == 4, (
        f"Expected data_size 4, got {ring_buf.data_size}"
    )

    # Initially writer_id=0, reader_id=0 -> lag = (0 - 0 + 10) % 10 = 0 (safe_lag = 9)
    assert not ring_buf.lag_not_is_safe()

    # Write integer data: 100 with args 200, 300
    ring_buf.set_data(100, 200, 300)

    # Manual checks after 1 write:
    # wid_buf[0] incremented to 1
    # data_header_buf[0] length set to 1 + 2 = 3
    assert ring_buf.wid_buf[0] == 1
    assert ring_buf.data_header_buf[0] == 3

    # Simulate reader lag beyond safe_lag threshold (safe_lag = 9)
    # Set wid=9, rid=0 -> lag = (9 - 0 + 10) % 10 = 9 -> 9 > 9 is False
    # Set wid=0, rid=0 -> lag = (0 - 0 + 10) % 10 = 0
    # Set wid=9, rid=0 with 1 more write advances wid to 0 -> lag = (0 - 0 + 10) % 10 = 0
    # Directly mock wid_buf to test boundary condition > safe_lag
    # Directly mock wid_buf and rid_buf to test boundary condition > safe_lag
    ring_buf.safe_lag = 8
    ring_buf.wid_buf[0] = 9
    ring_buf.rid_buf[0] = 0
    # Lag calculation: (9 - 0 + 10) % 10 = 9 -> 9 > 8 is True
    assert ring_buf.lag_not_is_safe(), "Expected lag_not_is_safe to be True"

    # Reset positions for read verification
    ring_buf.wid_buf[0] = 1
    ring_buf.rid_buf[0] = 0

    # Retrieve data
    retrieved_view = ring_buf.get_data()
    retrieved_list: list[Any] = list(retrieved_view)

    # Manual checks after read:
    # rid_buf[0] incremented to 1
    # retrieved integers match [100, 200, 300]
    assert ring_buf.rid_buf[0] == 1
    assert retrieved_list == [100, 200, 300], (
        f"Expected [100, 200, 300], got {retrieved_list}"
    )
