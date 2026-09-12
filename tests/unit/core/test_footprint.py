"""Unit tests for `imprint._core.footprint` models and JIT engine kernels."""

import numpy as np
import pytest
from numpy import float64, int64, intp
from numpy.typing import NDArray

from imprint._core import configs as cfg
from imprint._core import constant as c
from imprint._core.footprint.engine.reader import (
    _update_bar_states,
    _update_closed_bar_and_fp_states,
    _update_clusters_states,
    calc_value_area,
)
from imprint._core.footprint.engine.writer import (
    BHM_ConstantCount,
    FU_baseNprice,
    FU_baseTimestamp,
    FU_center,
    FU_ConstantCount,
    FU_fp_cols,
    FU_fp_rows,
    FU_idxDP,
    FU_idxVP,
    FU_price_mult,
    FU_price_prec,
    FU_qty_mult,
    FU_qty_prec,
    FU_scale,
    FU_tims,
    _update,
)
from imprint._core.footprint.models.base import FPArray
from imprint._core.footprint.models.converter import (
    Converter,
    to_idx,
    to_idy,
)
from imprint._core.settings import Timeframe


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


class TestFPJitKernel:
    def test_update_exact(self) -> None:
        # Setup test parameters
        args = np.zeros((FU_ConstantCount,), dtype=int64)
        args[FU_baseNprice] = 100_000  # 1000.00 with price_mult=100
        args[FU_fp_rows] = 100  # count idy
        args[FU_center] = 50  # idy center
        args[FU_scale] = 10  # 0.10 per tick/row
        args[FU_baseTimestamp] = 60000
        args[FU_tims] = 60000  # 1 minute per bar
        args[FU_fp_cols] = 10  # 5 bars (each bar has 2 columns: sell/buy)
        args[FU_idxVP] = -2
        args[FU_idxDP] = -1
        args[FU_price_mult] = 100
        args[FU_price_prec] = 2
        args[FU_qty_mult] = 10000
        args[FU_qty_prec] = 4

        footprint: NDArray[int64] = np.zeros((100, 12), dtype=int64)
        headers: NDArray[int64] = np.zeros((5, c.BH_ConstantCount), dtype=int64)
        headers_offset: memoryview = memoryview(bytearray(8)).cast("q")
        headers_offset[0] = 0
        bbox: NDArray[int64] = np.array([100, 10, 0, 0], dtype=int64)
        meta_data: NDArray[float64] = np.zeros(
            (2, BHM_ConstantCount), dtype=float64
        )

        # Execute trade 1: Buy 1.5 units at price 1000.50 at timestamp + 1000ms
        # Execute trade 2: Sell 0.5 units at price 1000.40 at timestamp + 2000ms
        # Execute trade 3: Sell 0.5 units at price 1000.40 at timestamp - 1000ms
        # Execute trade 4: Sell 0.5 units at price 1000.40 at timestamp + 10m
        # Execute trade 5: Sell 0.5 units at price 1020 at timestamp + 2000ms
        # Execute trade 5: Sell 0.5 units at price 930 at timestamp + 2000ms
        p, t = 100_000, 60_000
        for idx, (nPrice, nQty, timestamp, is_sell) in enumerate(
            zip(
                [p + 50, p + 40, p + 40, p + 40, p + 2000, p - 7000],
                [15_000, 5000, 5000, 5000, 5000, 5000],
                [t + 1000, t + 2000, t - 1000, t + 600_000, t + 2000, t + 2000],
                [0, 1, 1, 1, 1, 1],
            )
        ):
            result: int | None = _update(
                nPrice=int64(nPrice),
                nQty=int64(nQty),
                timestamp=int64(timestamp),
                is_sell=int64(is_sell),
                args=args,
                footprint=footprint,
                headers=headers,
                headers_offset=headers_offset,
                bbox=bbox,
                meta_data=meta_data,
            )
            if idx == 0:
                assert result is None

            if idx == 1:
                assert result is None

                for idy, idx, q in zip([45, 46], [1, 0], [15_000, nQty]):
                    assert footprint[idy, idx] == q
                    assert footprint[idy, args[FU_idxVP]] == q
                    assert footprint[idy, args[FU_idxDP]] == q if idx else -q

                bar = 0
                assert headers[bar, c.BH_CountTrade] == 2
                assert headers[bar, c.BH_Open] == p + 50
                assert headers[bar, c.BH_High] == p + 50
                assert headers[bar, c.BH_Low] == nPrice
                assert headers[bar, c.BH_Close] == nPrice
                assert headers[bar, c.BH_Volume] == 20_000  # 15000 + 5000
                assert (headers[bar, c.BH_Delta] == 10_000) and (
                    headers[bar, c.BH_CVD] == 10_000
                )  # 15000 (buy) - 5000 (sell)
                assert headers[bar, c.BH_Time] == t + 1000
                assert headers[bar, c.BH_LastTradeTime] == timestamp

                vol: float = 1.5 + 0.5
                p_vol: float = (1000.50 * 1.5) + (1000.40 * 0.5)
                p2_vol: float = (1000.50**2 * 1.5) + (1000.40**2 * 0.5)
                vwap: float = p_vol / vol
                variance: float = max(0.0, (p2_vol / vol - (vwap**2)))
                vwsd = np.sqrt(variance)
                upper_band = vwap + (2.0 * vwsd)
                lower_band = vwap - (2.0 * vwsd)
                assert headers[bar, c.BH_VWAP] == round(vwap * 100)
                assert headers[bar, c.BH_VWAP_UPPER_BAND] == round(
                    upper_band * 100
                )
                assert headers[bar, c.BH_VWAP_LOWER_BAND] == round(
                    lower_band * 100
                )

                assert bbox[0] == 45  # idYmin
                assert bbox[1] == 0  # idXmin
                assert bbox[2] == 47  # idYmax (46 + 1)
                assert bbox[3] == 2  # idXmax (1 + 1)

            elif result and ((idx == 2) or (idx == 3)):
                assert result & (c.RIF_session | c.RIF_idx)

            elif result and ((idx == 4) or (idx == 5)):
                assert result & (c.RIF_session | c.RIF_idy)

    def test_update_clusters_states_flags_delta_domination(self) -> None:
        fp: NDArray[int64] = np.zeros((4, 4), dtype=int64)
        fp_state: NDArray[int64] = np.zeros((4, 4), dtype=int64)
        idxVP, idxDP = 2, 3

        # Row 1 has positive delta (ask domination), row 2 has negative delta (bid domination)
        fp[1, idxDP] = 100
        fp[2, idxDP] = -100

        _update_clusters_states(
            idYmin=np.int64(0),
            idYmax=np.int64(4),
            idXmin=np.int64(0),
            idXmax=np.int64(2),
            idxVP=idxVP,
            idxDP=idxDP,
            fp=fp,
            fp_state=fp_state,
        )

        assert fp_state[1, idxVP] & c.SF_ASK_DELTA_DOMINATION_FP
        assert fp_state[2, idxVP] & c.SF_BID_DELTA_DOMINATION_FP

    def test_update_closed_bar_and_fp_states(self) -> None:
        # Setup test parameters
        lidx: int = 0  # bar = (0 & ~1) // 2 = 0
        idxVP: int = 2
        baseNprice: int64 = int64(1000)
        center: int64 = int64(5)
        scale: int = 10

        # Allocate inputs
        headers: NDArray[int64] = np.zeros((1, c.BH_ConstantCount), dtype=int64)
        headers_offset: memoryview = memoryview(np.array([0], dtype=int64))

        # Bar 0 header setup: High = 1030, Low = 970
        headers[0, c.BH_High] = 1030
        headers[0, c.BH_Low] = 970
        headers[0, c.BH_VWAP] = 1000
        headers[0, c.BH_VWAP_UPPER_BAND] = 1020
        headers[0, c.BH_VWAP_LOWER_BAND] = 980

        # Footprint matrix (10 rows x 3 columns)
        # Row indices corresponding to prices (idy = (baseNprice - price) // scale + center):
        # high_idy (1030) -> (1000 - 1030) // 10 + 5 = 2
        # low_idy  (970)  -> (1000 - 970)  // 10 + 5 = 8
        fp: NDArray[int64] = np.zeros((10, 3), dtype=int64)
        fp[2, idxVP] = 100  # Price 1030
        fp[3, idxVP] = 200  # Price 1020
        fp[4, idxVP] = 500  # Price 1010 -> POC (highest volume)
        fp[5, idxVP] = 300  # Price 1000
        fp[6, idxVP] = 100  # Price 990
        fp[7, idxVP] = 50  # Price 980
        fp[8, idxVP] = 10  # Price 970

        # Auction state volume setup at lidx + 1 = 1 (ask) and lidx = 0 (bid)
        fp[2, 1] = 0  # Ask = 0 -> High Finished Auction
        fp[8, 0] = 5  # Bid != 0 -> Low Unfinished Auction

        fp_state: NDArray[int64] = np.zeros((10, 3), dtype=int64)
        fp_state_cache: NDArray[int64] = np.zeros(
            (c.CSD_ConstantCount,), dtype=int64
        )

        _update_closed_bar_and_fp_states(
            lidx=lidx,
            idxVP=idxVP,
            headers=headers,
            headers_offset=headers_offset,
            fp=fp,
            fp_state=fp_state,
            fp_state_cache=fp_state_cache,
            baseNprice=baseNprice,
            center=center,
            scale=scale,
        )

        # 1. ATR calculation for bar 0: High - Low = 1030 - 970 = 60
        assert headers[0, c.BH_ATR] == int64(60)
        # 2. PARK calculation: round(ln(1030 / 970)^2 * 1_000_000_000)
        assert headers[0, c.BH_PARK] == int64(3_602_161)

        # 3. VWAP & Bollinger Bands row indices mapping:
        # vwap (1000)      -> (1000 - 1000) // 10 + 5 = 5
        # upper_bb (1020)  -> (1000 - 1020) // 10 + 5 = 3
        # lower_bb (980)   -> (1000 - 980)  // 10 + 5 = 7
        assert fp_state_cache[c.CSD_VWAP] == int64(5)
        assert fp_state_cache[c.CSD_UPPER_BB] == int64(3)
        assert fp_state_cache[c.CSD_LOWER_BB] == int64(7)

        assert fp_state[5, idxVP] & c.SF_VWAP_FP
        assert fp_state[3, idxVP] & c.SF_UPPER_BAND_FP
        assert fp_state[7, idxVP] & c.SF_LOWER_BAND_FP

        # 4. Volume Profile, POC, and Value Area (VAH / VAL):
        # Total volume = 100 + 200 + 500 + 300 + 100 + 50 + 10 = 1260
        # Target volume (70%) = 1260 * 0.70 = 882.0
        # POC = row 4 (volume = 500).
        # Step 1: Up (row 3, vol 200) vs Down (row 5, vol 300) -> Pick Down (row 5). Total = 500 + 300 = 800
        # Step 2: Up (row 3, vol 200) vs Down (row 6, vol 100) -> Pick Up (row 3). Total = 800 + 200 = 1000 (>= 882.0, Done!)
        # VAH = row 3, VAL = row 5
        assert fp_state_cache[c.CSD_POC_FP] == int64(4)
        assert fp_state_cache[c.CSD_VAH_FP] == int64(3)
        assert fp_state_cache[c.CSD_VAL_FP] == int64(5)

        assert fp_state[4, idxVP] & c.SF_POC_FP
        assert fp_state[3, idxVP] & c.SF_VAH_FP
        assert fp_state[5, idxVP] & c.SF_VAL_FP

        # Header prices: (center - idy) * scale + baseNprice
        # POC price: (5 - 4) * 10 + 1000 = 1010
        # VAH price: (5 - 3) * 10 + 1000 = 1020
        # VAL price: (5 - 5) * 10 + 1000 = 1000
        assert headers[0, c.BH_POC_FP] == int64(1010)
        assert headers[0, c.BH_VAH_FP] == int64(1020)
        assert headers[0, c.BH_VAL_FP] == int64(1000)

        # 5. Auction states:
        # High idy (2): ask == 0 -> Finished Auction
        # Low idy (8): bid != 0 -> Unfinished Auction
        assert fp_state[2, idxVP] & c.SF_FINISHED_AUCTION
        assert fp_state[8, idxVP] & c.SF_UNFINISHED_AUCTION

    def test_update_bar_states_exact(self) -> None:
        baseNprice: int64 = int64(100_000)
        center: int64 = int64(50)
        scale: int64 = int64(10)
        fp_rows: int = 100
        fp_cols: int = 4

        fp: NDArray[int64] = np.zeros((fp_rows, fp_cols), dtype=int64)
        fp_state: NDArray[int64] = np.zeros((fp_rows, fp_cols), dtype=int64)
        headers: NDArray[int64] = np.zeros(
            (10, c.BH_ConstantCount), dtype=int64
        )
        headers_offset: memoryview = memoryview(bytearray(8)).cast("q")
        headers_offset[0] = 0

        bar: int = 0
        idxBid: int = 0
        idxAsk: int = 1

        # Define OHLC prices (fixed-point)
        # open=100_000, high=100_020, low=99_980, close=100_010
        openNprice: int64 = int64(100_000)
        highNprice: int64 = int64(100_020)
        lowNprice: int64 = int64(99_980)
        closeNprice: int64 = int64(100_010)

        headers[bar, c.BH_Open] = openNprice
        headers[bar, c.BH_High] = highNprice
        headers[bar, c.BH_Low] = lowNprice
        headers[bar, c.BH_Close] = closeNprice

        # Corresponding idy values:
        # open_idy = (100000 - 100000) // 10 + 50 = 50
        # high_idy = (100000 - 100020) // 10 + 50 = 48
        # low_idy  = (100000 - 99980)  // 10 + 50 = 52
        # close_idy = (100000 - 100010) // 10 + 50 = 49

        # Populate footprint data for rows 48 to 52 (inclusive)
        # bid (idxBid=0), ask (idxAsk=1)
        # Row 48 (high): bid=10, ask=5
        # Row 49: bid=100, ask=20 (imbalance: 100 > 20*3 -> True)
        # Row 50: bid=5, ask=0 (zero print for ask if shifted, let's test specific ZP)
        # Row 51: bid=0, ask=50 (zero print for bid)
        # Row 52 (low): bid=10, ask=10

        for idy, bid_v, ask_v in zip(
            range(48, 53), [10, 100, 5, 0, 10], [5, 20, 0, 50, 10]
        ):
            fp[idy, idxBid] = bid_v
            fp[idy, idxAsk] = ask_v

        idYmin: int64 = int64(47)
        idYmax: int64 = int64(53)

        _update_bar_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idxBid=idxBid,
            idxAsk=idxAsk,
            headers=headers,
            headers_offset=headers_offset,
            fp=fp,
            fp_state=fp_state,
            baseNprice=baseNprice,
            center=center,
            scale=int(scale),
        )

        # 1. Check OHLC state flags
        assert fp_state[50, idxBid] & c.SF_OPEN, "Open state flag missing"
        assert fp_state[48, idxBid] & c.SF_HIGH, "High state flag missing"
        assert fp_state[52, idxBid] & c.SF_LOW, "Low state flag missing"
        assert fp_state[49, idxBid] & c.SF_CLOSE, "Close state flag missing"
        # 2. Check Imbalance flag at row 49 (bid=100, ask=20 -> 100 > 60)
        assert fp_state[49, idxBid] & c.SF_IMBALANCE, (
            "Bid imbalance flag missing"
        )
        # 4. Check POC and Value Area headers calculation
        # vp_bar for rows 48..52:
        # row 48: 10 + 5 = 15
        # row 49: 100 + 20 = 120 (POC because max volume)
        # row 50: 5 + 0 = 5
        # row 51: 0 + 50 = 50
        # row 52: 10 + 10 = 20
        # Total volume = 15 + 120 + 5 + 50 + 20 = 210
        assert headers[bar, c.BH_POC] == int64(
            (center - (48 + 1)) * scale + baseNprice
        )
        assert fp_state[49, idxBid] & c.SF_POC_BAR, "POC bar state flag missing"

    def test_calc_value_area_exact(self) -> None:
        vp_slice: NDArray[int64] = np.array(
            [10, 20, 15, 30, 40, 15, 10, 5], dtype=np.int64
        )
        center_idx: intp = np.argmax(vp_slice)  # 4

        assert center_idx == 4, "Incorrect test"

        val_idx: intp
        vah_idx: intp
        val_idx, vah_idx = calc_value_area(vp_slice, center_idx)

        expected_val_idx: int = 1
        expected_vah_idx: int = 5

        assert val_idx == expected_val_idx, (
            f"Expected VAL[{expected_val_idx}], got {val_idx}"
        )
        assert vah_idx == expected_vah_idx, (
            f"Expected VAH[{expected_vah_idx}], got {vah_idx}"
        )


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
    coin_cfg = cfg.Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")
    fp_cfg = cfg.Footprint(
        timeframe=Timeframe.H1,
        chart_range=1,
        step_tick=1,
        fp_rows=10001,
    )
    return Converter(cfgCoin=coin_cfg, cfgFP=fp_cfg)


class TestFPConverter:
    def test_converter_initialization(self, converter: Converter) -> None:
        """Verifies fields initialized during __post_init__ match expected constant values."""
        assert converter.tick_size == "0.01"
        assert converter.price_prec == 2
        assert converter.price_mult == 100
        assert converter.qty_prec == 3
        assert converter.qty_mult == 1000
        assert converter.timeframe == "H1"
        assert converter.tims == 3_600_000
        assert converter.chart_range == 1
        assert converter.step_tick == 1
        assert converter.fp_rows == 10001
        assert converter.fp_cols == 48
        assert converter.fp_panel_cols == 50
        assert converter.bar_count == 24
        assert converter.idxVP == -2
        assert converter.idxDP == -1
        assert converter.scale == 1
        assert converter.total_bar_count == 24

    def test_converter_initialization_with_total_backtest_days(self) -> None:
        """Verifies total_bar_count calculation when total_backtest_days is specified."""
        coin_cfg = cfg.Coin(
            symbol="BTCUSDT", tick_size="0.01", lot_size="0.001"
        )
        fp_cfg = cfg.Footprint(timeframe=Timeframe.H1, chart_range=1)
        conv = Converter(cfgCoin=coin_cfg, cfgFP=fp_cfg, total_backtest_days=5)

        # 5 days * 24 h/day * 60 min/h * 60 s/min * 1000 ms/s = 432_000_000 ms
        # 432_000_000 // 3_600_000 = 120 bars
        assert conv.total_bar_count == 120

    def test_init_session(self, converter: Converter) -> None:
        """Verifies session calibration for base price, timestamp alignment, and grid center."""
        n_price = int64(500_055)  # 5000.55
        timestamp = int64(3_660_000)  # 01:01

        converter.init_session(n_price, timestamp)

        # baseNprice = (500_055 // 1) * 1 = 500_055
        # baseTimestamp = 3_660_000 - (3_660_000 % 3_600_000) = 3_660_000 - 60_000 = 3_600_000 # 01:00
        # center = 10_001 // 2 = 5_000
        assert converter.baseNprice == int64(500_055)
        assert converter.baseTimestamp == int64(3_600_000)
        assert converter._first_base_timestamp == int64(3_600_000)
        assert converter.center == int64(5_000)

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
        base_n_price: int64 = int64(10_000)
        scale: int = 10
        center: int64 = int64(500)
        fp_rows: int64 = int64(1000)

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
        base_timestamp: int64 = int64(1000)
        tims: int = 100
        fp_cols: int = 10

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
