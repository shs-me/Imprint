import numpy as np
import pytest
from numpy import int64

from imprint._core import configs as cfg
from imprint._core.footprint.models.converter import Converter, to_idx, to_idy
from imprint._core.settings import Timeframe
from imprint._core.utils import FPArray


class TestFPArray:
    def test_initialization_and_zero_fill(self) -> None:
        arr: FPArray = FPArray(rows=10, cols=5)
        assert arr.shape == (10, 5)
        assert np.all(arr == 0)

    def test_padding_adds_rows_correctly(self) -> None:
        arr: FPArray = FPArray(rows=4, cols=2)
        arr[0, 0] = 42
        padded: FPArray = arr.padding(before=2, after=3)
        assert padded.shape == (9, 2)
        assert padded[2, 0] == 42
        assert isinstance(padded, FPArray)


@pytest.fixture
def converter() -> Converter:
    """Fixture providing initialized Converter with deterministic parameters.

    Coin configuration:
        tick_size = "0.01", lot_size = "0.001"
        price_prec = 2, price_mult = 100
        qty_prec = 3, qty_mult = 1000

    Footprint configuration:
        timeframe = Timeframe.H1 (3_600_000 ms)
        chart_range = 1 day -> bar_count = 24
        step_tick = 1
        fp_rows = 10001
        colVP = -2, colDP = -1
        fp_cols = 48, fp_panel_cols = 50

    Derived properties:
        scale = round(0.01 * 1 * 100) = 1
        total_bar_count = 24
    """
    coin = cfg.Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")
    fp = cfg.Footprint(timeframe=Timeframe.H1, chart_range=1, step_tick=1)
    con = Converter()
    con.post_init(coin, fp, 0)
    return con


class TestFPConverter:
    def test_converter_initialization(self, converter: Converter) -> None:
        """Verifies fields initialized during __post_init__ match expected constant values."""
        assert converter.tick_size == "0.01"
        assert converter.price_prec[0] == 2
        assert converter.price_mult[0] == 100
        assert converter.qty_prec[0] == 3
        assert converter.qty_mult[0] == 1000
        assert converter.timeframe[0] == "H"
        assert converter.tims[0] == 3_600_000
        assert converter.chart_range[0] == 1
        assert converter.step_tick[0] == 1
        assert converter.fp_rows[0] == 10001
        assert converter.fp_cols[0] == 48
        assert converter.fp_panel_cols[0] == 50
        assert converter.bar_count[0] == 24
        assert converter.idxVP[0] == -2
        assert converter.idxDP[0] == -1
        assert converter.scale[0] == 1
        assert converter.total_bar_count == 24

    def test_converter_initialization_with_total_backtest_days(self) -> None:
        """Verifies total_bar_count calculation when total_backtest_days is specified."""
        coin = cfg.Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")
        fp = cfg.Footprint(timeframe=Timeframe.H1, chart_range=1)
        con = Converter()
        con.post_init(coin, fp, 5)

        # 5 days * 24 h/day * 60 min/h * 60 s/min * 1000 ms/s = 432_000_000 ms
        # 432_000_000 // 3_600_000 = 120 bars
        assert con.total_bar_count == 120

    def test_init_session(self, converter: Converter) -> None:
        """Verifies session calibration for base price, timestamp alignment, and grid center."""
        n_price = int64(500_055)  # 5000.55
        timestamp = int64(3_660_000)  # 01:01

        converter.init_session(n_price, timestamp)

        # baseNprice = (500_055 // 1) * 1 = 500_055
        # baseTimestamp = 3_660_000 - (3_660_000 % 3_600_000) = 3_660_000 - 60_000 = 3_600_000 # 01:00
        # center = 10_001 // 2 = 5_000
        assert converter.baseNprice[0] == int64(500_055)
        assert converter.baseTimestamp[0] == int64(3_600_000)
        assert converter._first_base_timestamp == int64(3_600_000)
        assert converter.center[0] == int64(5_000)

    def test_to_idy_mapping(self, converter: Converter) -> None:
        """Verifies price to Y-axis grid row mapping for exact, upper bound, lower bound, and out-of-bounds prices."""
        converter.init_session(
            nPrice=int64(500_000), timestamp=int64(3_600_000)
        )
        # baseNprice = 500000, scale = 1, center = 5000, fp_rows = 10001
        # formula: idy = (baseNprice - nPrice) // scale + center
        p = 500_000
        for nPrice, test_value in zip(
            [p, p + 1000, p - 3000, p + 4999, p + 5000, p + 6000, p - 5000 - 1],
            [5000, 4000, 8000, 1, 0, None, None],
        ):
            # Exact base price -> center row 5000
            # Higher price -> lower Y row
            # nPrice = 501_000: (500_000 - 501_000) // 1 + 5000 = 4000
            # Lower price -> higher Y row
            # nPrice = 497_000: (500_000 - 497_000) // 1 + 5000 = 8000
            # Boundary tests
            # idy = 1 -> nPrice = 504_999: (500_000 - 504_999) // 1 + 5000 = 1
            # Out of bounds (idy <= 0 returns None)
            # idy = 0 -> nPrice = 505_000: (500_000 - 506_000) // 1 + 5000 = <0
            # Out of bounds (idy >= fp_rows)
            # idy = 10001 -> nPrice = 494999 -> None
            assert converter.to_idy(int64(nPrice)) == test_value

    def test_to_idx_mapping(self, converter: Converter) -> None:
        """Verifies timestamp and trade side to X-axis grid column mapping."""
        converter.init_session(
            nPrice=int64(500_000),  # 5000.00
            timestamp=int64(3_600_000),  # 01:00
        )
        # baseTimestamp = 3_600_000, tims = 3_600_000, fp_cols = 48
        # formula: idx = (timestamp - baseTimestamp) // tims * 2 + (0 if is_sell else 1)

        t = 3_600_000
        for timestamp, is_sell, test_value in zip(
            [t, t, t * 2, t * 2, t * 24, t * 24, t * 25, t - 1],
            [1, 0, 1, 0, 1, 0, 0, 0],
            [0, 1, 2, 3, 46, 47, None, None],
        ):
            # First BID bar is 0
            # First ASK bar is 1
            # Second BID bar is 2
            # Second ASK bar is 3
            # Last BID bar is 46 (fp_cols = 48, max valid bid index = 46)
            # Last ASK bar is 47 (fp_cols = 48, max valid index = 47)
            # Out of bounds (idx >= fp_cols = 48)
            # Out of bounds (0 > idx)
            assert (
                converter.to_idx(int64(timestamp), is_sell=int64(is_sell))
                == test_value
            )

    def test_conversions(self, converter: Converter) -> None:
        """Verifies row-to-fixed-price, quantity, price float/int, and strftime conversions."""
        converter.init_session(
            nPrice=int64(500000), timestamp=int64(1700000000000)
        )
        # center = 5000, scale = 1, baseNprice = 500000

        # to_nPrice: (center - idy) * scale + baseNprice
        # (5000 - 4000) * 1 + 500000 = 501000
        assert converter.to_nPrice(4000) == int64(501000)
        assert converter.to_nPrice(int64(6000)) == int64(499000)
        # to_nQty: round(qty * qty_mult) with qty_mult = 1000
        assert converter.to_nQty(1.23456) == 1235
        assert converter.to_nQty(0.001) == 1
        # to_price: nPrice / price_mult with price_mult = 100
        assert converter.to_price(int64(500055)) == 5000.55
        # to_qty: nQty / qty_mult with qty_mult = 1000
        assert converter.to_qty(int64(1234)) == 1.234
        # to_strftime
        assert converter.to_strftime(1700000000000) == "2023-11-14"
        # get_price: round(to_price(to_nPrice(idy)), price_prec)
        # idy = 4000 -> nPrice = 501000 -> price = 5010.0
        assert converter.get_price(4000) == 5010.0

    def test_get_time(self, converter: Converter) -> None:
        """Verifies column index X to timestamp and formatted UTC date string lookup."""
        converter.init_session(
            nPrice=int64(500_000), timestamp=int64(3_600_000)
        )
        # tims = 3_600_000, baseTimestamp = 3_600_000
        # formula: (idx & ~1) // 2 * tims + baseTimestamp
        t = 3_600_000
        for idx, test_value in zip(range(4), [t, t, t * 2, t * 2]):
            # idx = 0 or 1 -> bar 0 timestamp = 3_600_000
            # idx = 2 or 3 -> bar 1 timestamp = 3_600_000 + 3_600_000
            assert converter.get_time(int64(idx)) == int64(test_value)

        # strftime = True returning formatted date string
        assert converter.get_time(0, strftime=True) == "1970-01-01"

    def test_numba_to_idy_function(self) -> None:
        """Verifies standalone Numba-compiled to_idy low-level function directly."""
        base_n_price: memoryview = memoryview(bytearray(8)).cast("q")
        scale: memoryview = memoryview(bytearray(8)).cast("q")
        center: memoryview = memoryview(bytearray(8)).cast("q")
        fp_rows: memoryview = memoryview(bytearray(8)).cast("q")
        base_n_price[0] = 10_000
        scale[0] = 10
        center[0] = 500
        fp_rows[0] = 1000

        for nPrice, test_value in zip(
            [10_000, 10_100, 15000, 15010, 5000], [500, 490, 0, -1, -1]
        ):
            # idy = (10_000 - 10_000) // 10 + 500 = 500
            # idy = (10_000 - 10_100) // 10 + 500 = 490
            # Upper bound check (0 <= idy < 1000)
            # idy = (10_000 - 15_000) // 10 + 500 = 0 -> valid
            # Out of bounds low: idy = (10_000 - 15010) // 10 + 500 = -1 -> returns -1
            # Out of bounds high: idy = (10_000 - 5000) // 10 + 500 = 1000 -> returns -1
            assert (
                to_idy(int64(nPrice), base_n_price, scale, center, fp_rows)
                == test_value
            )

    def test_numba_to_idx_function(self) -> None:
        """Verifies standalone Numba-compiled to_idx low-level function directly."""
        base_timestamp: memoryview = memoryview(bytearray(8)).cast("q")
        tims: memoryview = memoryview(bytearray(8)).cast("q")
        fp_cols: memoryview = memoryview(bytearray(8)).cast("q")
        base_timestamp[0] = 1000
        tims[0] = 100
        fp_cols[0] = 10

        for timestamp, is_sell, test_value in zip(
            [1000, 1000, 1400, 1500, 900], [1, 0, 0, 1, 1], [0, 1, 9, -1, -1]
        ):
            # idx = (1000 - 1000) // 100 * 2 + 0 = 0
            # idx = (1000 - 1000) // 100 * 2 + 1 = 1
            # idx = (1400 - 1000) // 100 * 2 + 1 = 9
            # Out of bounds high: idx = (1500 - 1000) // 100 * 2 + 0 = 10 -> returns -1
            # Out of bounds low: idx = (900 - 1000) // 100 * 2 + 0 = -2 -> returns -1
            assert (
                to_idx(
                    timestamp=int64(timestamp),
                    is_sell=int64(is_sell),
                    baseTimestamp=base_timestamp,
                    tims=tims,
                    fp_cols=fp_cols,
                )
                == test_value
            )
