import inspect
from collections import deque
from dataclasses import dataclass, field

import pytest
from numpy import random

from imprint._core import configs as cfg
from imprint._core.settings import Timeframe


class TestConfigurationPostInitAction:
    @pytest.mark.parametrize(
        "pct", [0.0, 0.01, 0.05, 1.0, 10.0, 50.5, 100.0, 1e-4]
    )
    def test_percent_calculation(self, pct: float) -> None:
        """Verify manual fixed-point percent calculation across fractional, integer, and edge-case values."""
        expected_fixed = round(pct / 100 * cfg.PERCENT)
        percent = cfg.Percent(pct)
        assert percent.fixed == expected_fixed, (
            f"Expected percent fixed value {expected_fixed} for {pct}%, got {percent.fixed}"
        )

    def test_account_scale_mult(self) -> None:
        """Verify Account scale multiplier initialization."""
        account = cfg.Account(scale_prec=8)
        expected_mult: int = 10**8
        assert account.scale_mult == expected_mult, (
            f"Expected scale multiplier {expected_mult}, got {account.scale_mult}"
        )

    @pytest.mark.parametrize(
        ("tick_size", "lot_size", "exp_price_prec", "exp_qty_prec"),
        [
            ("0.01", "0.001", 2, 3),
            ("1e-8", "1e-4", 8, 4),
            ("0.00000001", "0.0001", 8, 4),
            ("1", "1", 0, 0),
            ("100", "1000", 0, 0),
            ("1e+2", "1e+3", 0, 0),
            ("0.1", "10", 1, 0),
            ("1e-5", "1", 5, 0),
        ],
    )
    def test_coin_precisions_and_multipliers(
        self,
        tick_size: str,
        lot_size: str,
        exp_price_prec: int,
        exp_qty_prec: int,
    ) -> None:
        """Verify Coin precision parsing and derived multiplier calculations across fractions, integers, and scientific notations."""
        coin = cfg.Coin(
            symbol="TESTUSDT", tick_size=tick_size, lot_size=lot_size
        )

        assert coin.price_prec == exp_price_prec, (
            f"Expected price_prec {exp_price_prec} for tick_size '{tick_size}', got {coin.price_prec}"
        )
        assert coin.qty_prec == exp_qty_prec, (
            f"Expected qty_prec {exp_qty_prec} for lot_size '{lot_size}', got {coin.qty_prec}"
        )
        assert coin.price_mult == 10**exp_price_prec, (
            f"Expected price_mult {10**exp_price_prec}, got {coin.price_mult}"
        )
        assert coin.qty_mult == 10**exp_qty_prec, (
            f"Expected qty_mult {10**exp_qty_prec}, got {coin.qty_mult}"
        )

    def test_footprint_bar_count_and_columns(self) -> None:
        """Verify Footprint bar count and panel column calculations."""
        fp = cfg.Footprint(timeframe=Timeframe.H1, chart_range=1)

        exp_bar_count: int = 24
        exp_fp_cols: int = 48
        exp_fp_panel_cols: int = 50

        assert fp.bar_count == exp_bar_count, (
            f"Expected bar_count {exp_bar_count}, got {fp.bar_count}"
        )
        assert fp.fp_cols == exp_fp_cols, (
            f"Expected fp_cols {exp_fp_cols}, got {fp.fp_cols}"
        )
        assert fp.fp_panel_cols == exp_fp_panel_cols, (
            f"Expected fp_panel_cols {exp_fp_panel_cols}, got {fp.fp_panel_cols}"
        )


@pytest.mark.parametrize(
    "shm_cls",
    [
        cls
        for _, cls in inspect.getmembers(cfg, inspect.isclass)
        if issubclass(cls, cfg.MemoryLayout) and cls is not cfg.MemoryLayout
    ],
)
def test_memory_layouts_invariants(
    shm_cls: type[cfg.MemoryLayout],
) -> None:
    """
    Verify memory layout and shared memory segment invariants:
    - Layout size is strictly positive.
    - Layout size is page-aligned (multiple of 4096) when alignment is enabled (`align=True`), or matches exact total segment offset when disabled (`align=False`).
    - Layout contains at least one segment, and all defined layout slots corresponding to Segment or RingBuf instances are present in their respective collections (`segments`, `rings`).
    - Segments are contiguous without memory gaps, meaning each segment's start offset matches the previous segment's end offset.
    - Each segment's end bound equals its start offset plus its size.
    - Total contiguous segment size does not exceed the layout size (and equals layout size when `align=False`).
    - Bound memory views match respective segment sizes.
    """
    layout: cfg.MemoryLayout = shm_cls(align=True)

    assert layout.size > 0, (
        f"{shm_cls}: Layout size must be strictly positive, got {layout.size}"
    )
    assert layout.size % 4096 == 0, (
        f"{shm_cls}: Layout size must be page-aligned (multiple of 4096), got {layout.size}"
    )

    assert len(layout.segments) > 0, f"{shm_cls}: Layout contains no segments"

    for name in layout.__slots__:
        seg_names = str(layout.segments.keys())
        rings_names = str(layout.rings.keys())
        obj = getattr(layout, name)
        if isinstance(obj, cfg.Segment):
            assert name in seg_names, (
                f"{shm_cls}: Segment slot '{name}' not found in layout.segments"
            )

        elif isinstance(obj, cfg.RingBuf):
            assert name in rings_names, (
                f"{shm_cls}: RingBuf slot '{name}' not found in layout.rings"
            )
            for attr_name in obj.__slots__:
                if hasattr(obj, attr_name):
                    attr_obj = getattr(obj, attr_name)
                    if isinstance(attr_obj, cfg.Segment):
                        attr_name = f"{name}_{attr_name}"
                        assert attr_name in seg_names, (
                            f"{shm_cls}: RingBuf Segment slot '{attr_name}' not found in layout.segments"
                        )

    current_offset: int = 0
    for name, seg in layout.segments.items():
        assert seg.offset is not None, f"Segment {name} has no offset assigned"
        start, end = seg.offset

        assert start == current_offset, (
            f"Memory gap before {name}: expected {current_offset}, got {start}"
        )
        assert end == start + seg.size, (
            f"Incorrect slice size for {name}: size={seg.size}, but end-start={end - start}"
        )
        current_offset = end

    assert current_offset <= layout.size, (
        f"{shm_cls}: Total contiguous segment size ({current_offset}) exceeds layout size ({layout.size})"
    )

    buf: memoryview = memoryview(bytearray(layout.size))
    layout.bind_memory(buf)
    for name, seg in layout.segments.items():
        assert seg.view is not None, f"Segment {name} is not bound to a buffer"
        assert seg.view.nbytes == seg.size, (
            f"Incorrect buffer size for {name}: size={seg.size}, but view={seg.view.nbytes}."
        )

    layout = shm_cls(align=False)
    assert current_offset == layout.size, (
        f"{shm_cls}: Unaligned layout size ({layout.size}) does not match total segment offset ({current_offset})"
    )


def test_ring_buf_invariants() -> None:
    """
    Verify ring buffer invariants:
    - Ring buffer data set/get roundtrips correctly.
    - Exceeding `data_size` raises a `ValueError` during data assignment (`set_data`).
    - Lag safety checks correctly detect and handle reader/writer pointer divergence/overflow conditions.
    - Ring indices and cell pointers (`wid_buf`, `rid_buf`) reset correctly to zero upon calling `reset()`.
    """

    @dataclass(slots=True)
    class RingLayout(cfg.MemoryLayout):
        ring_raw: cfg.RingBuf = field(
            default_factory=lambda: cfg.RingBuf(
                data_size=24, cell_amount=10, count_writer=2, count_reader=2
            )
        )
        ring_casted: cfg.RingBuf = field(
            default_factory=lambda: cfg.RingBuf(
                data_size=24,
                cell_amount=10,
                count_writer=2,
                count_reader=2,
                cast_to_int64=True,
            )
        )

    def check_read_data(ring: cfg.RingBuf, reader: int, payload: bytes) -> None:
        read_data = ring.get_data(reader)
        assert bytes(read_data) == payload, (
            f"expected {payload}, got {bytes(read_data)}, reader {reader}, cell {ring.rid_buf[0]}"
        )
        if ring.cast_to_int64:
            try:
                _a, _b, _c = read_data
            except ValueError:
                raise AssertionError(
                    "variable unpacking failed for casted buffer."
                )

    layout = RingLayout()
    layout.bind_memory(memoryview(bytearray(layout.size)))
    layout.post_init_rings()
    rng = random.default_rng()
    test_data = rng.integers(2**63, size=(30, 3))

    for name, ring in layout.rings.items():
        with pytest.raises(ValueError):
            ring.set_data(bytes(ring.data_size + 1))

        exp_data: deque[memoryview] = deque()
        for _ in range(ring.cell_amount * 3):
            payload: memoryview = rng.choice(test_data).data
            if not ring.cast_to_int64:
                payload = payload.cast("B")

            if ring.lag_not_is_safe() is False:
                ring.set_data(payload)
                check_read_data(ring, 0, bytes(payload))
                assert ring.wid_buf[0] != ring.rid_buf[1], (
                    f"Ring {name}: expected safety check trigger"
                )
                exp_data.append(payload)
            else:
                while exp_data:
                    payload = exp_data.popleft()
                    check_read_data(ring, 1, bytes(payload))

                assert ring.lag_not_is_safe() is False, (
                    f"Ring {name}: expected pass"
                )

        ring.reset()
        for _ in range(2):
            if _ == 0:
                ring.reset()
            else:
                layout.reset()

            for wid, rid in zip(
                range(ring.count_writer), range(ring.count_reader)
            ):
                assert ring.wid_buf[wid] == 0, (
                    f"Ring {name}: writer cell pointer not reset"
                )
                assert ring.rid_buf[rid] == 0, (
                    f"Ring {name}: reader cell pointer not reset"
                )
                ring.wid_buf[wid] = 1
                ring.rid_buf[rid] = 1
