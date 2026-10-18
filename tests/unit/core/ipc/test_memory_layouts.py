import inspect
from collections import deque
from dataclasses import dataclass, field

import pytest
from numpy import random

import imprint._core.ipc.memory_layouts as ml


@pytest.mark.parametrize(
    "ml_cls",
    [
        cls
        for _, cls in inspect.getmembers(ml, inspect.isclass)
        if issubclass(cls, ml.MemoryLayout) and (cls is not ml.MemoryLayout)
    ],
)
def test_memory_layouts_invariants(
    ml_cls: type[ml.MemoryLayout],
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
    layout: ml.MemoryLayout = ml_cls(align=True)

    assert layout.size > 0, (
        f"{ml_cls}: Layout size must be strictly positive, got {layout.size}"
    )
    assert layout.size % 4096 == 0, (
        f"{ml_cls}: Layout size must be page-aligned (multiple of 4096), got {layout.size}"
    )

    assert len(layout.segments) > 0, f"{ml_cls}: Layout contains no segments"

    for name in layout.__slots__:
        seg_names = str(layout.segments.keys())
        rings_names = str(layout.rings.keys())
        obj = getattr(layout, name)
        if isinstance(obj, ml.Segment):
            assert name in seg_names, (
                f"{ml_cls}: Segment slot '{name}' not found in layout.segments"
            )

        elif isinstance(obj, ml.RingBuf):
            assert name in rings_names, (
                f"{ml_cls}: RingBuf slot '{name}' not found in layout.rings"
            )
            for attr_name in obj.__slots__:
                if hasattr(obj, attr_name):
                    attr_obj = getattr(obj, attr_name)
                    if isinstance(attr_obj, ml.Segment):
                        attr_name = f"{name}_{attr_name}"
                        assert attr_name in seg_names, (
                            f"{ml_cls}: RingBuf Segment slot '{attr_name}' not found in layout.segments"
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
        f"{ml_cls}: Total contiguous segment size ({current_offset}) exceeds layout size ({layout.size})"
    )

    buf: memoryview = memoryview(bytearray(layout.size))
    layout.bind_memory(buf)
    for name, seg in layout.segments.items():
        assert seg.view is not None, f"Segment {name} is not bound to a buffer"
        assert seg.view.nbytes == seg.size, (
            f"Incorrect buffer size for {name}: size={seg.size}, but view={seg.view.nbytes}."
        )

    layout = ml_cls(align=False)
    assert current_offset == layout.size, (
        f"{ml_cls}: Unaligned layout size ({layout.size}) does not match total segment offset ({current_offset})"
    )


def test_ring_buf_invariants() -> None:
    """
    Verify ring buffer invariants:
    - Ring buffer data set/get roundtrips correctly.
    - Exceeding `cell_size` raises a `ValueError` during data assignment (`set_data`).
    - Lag safety checks correctly detect and handle reader/writer pointer divergence/overflow conditions.
    - Ring indices and cell pointers (`wid_buf`, `rid_buf`) reset correctly to zero upon calling `reset()`.
    """

    @dataclass(slots=True)
    class RingLayout(ml.MemoryLayout):
        ring_raw: ml.RingBuf = field(
            default_factory=lambda: ml.RingBuf(
                cell_size=24, cell_amount=10, count_writer=2, count_reader=2
            )
        )
        ring_casted: ml.RingBuf = field(
            default_factory=lambda: ml.RingBuf(
                cell_size=24,
                cell_amount=10,
                count_writer=2,
                count_reader=2,
                cast_to_int64=True,
            )
        )

    def check_read_data(ring: ml.RingBuf, reader: int, payload: bytes) -> None:
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
            ring.set_data(bytes(ring.cell_size + 1))

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
