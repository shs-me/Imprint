"""Unit tests for `imprint.core.footprint.models.con.Converter`."""

import numpy as np
import pytest

from imprint.core.configs import Coin, Footprint
from imprint.core.footprint.models.converter import Converter
from imprint.core.settings import Timeframe


@pytest.fixture
def con() -> Converter:
    coin = Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")
    fp_cfg = Footprint(timeframe=Timeframe.M5, chart_range=1, step_tick=5)
    conv = Converter(cfgCoin=coin, cfgFP=fp_cfg, total_backtest_days=0)
    conv.init_session(
        nPrice=np.int64(10_000_00), timestamp=np.int64(1_700_000_400_000)
    )
    return conv


class TestPostInit:
    def test_price_and_qty_multipliers_come_from_coin(
        self, con: Converter
    ) -> None:
        assert con.price_mult == 100
        assert con.qty_mult == 1_000

    def test_scale_is_tick_size_times_step_tick_times_price_mult(self):
        coin = Coin(tick_size="0.01", lot_size="0.001")
        fp_cfg = Footprint(timeframe=Timeframe.M5, step_tick=5)
        conv = Converter(cfgCoin=coin, cfgFP=fp_cfg)
        assert conv.scale == 5

    def test_total_bar_count_falls_back_to_bar_count_without_backtest_days(
        self,
    ) -> None:
        coin = Coin(tick_size="0.01", lot_size="0.001")
        fp_cfg = Footprint(timeframe=Timeframe.M5, chart_range=1)
        conv = Converter(cfgCoin=coin, cfgFP=fp_cfg, total_backtest_days=0)
        assert conv.total_bar_count == fp_cfg.bar_count

    def test_total_bar_count_scales_with_backtest_days(self):
        coin = Coin(tick_size="0.01", lot_size="0.001")
        fp_cfg = Footprint(timeframe=Timeframe.M5, chart_range=1)
        conv = Converter(cfgCoin=coin, cfgFP=fp_cfg, total_backtest_days=7)
        assert conv.total_bar_count == (7 * 24 * 60 * 60 * 1000) // int(
            Timeframe.M5
        )


class TestInitSession:
    def test_base_price_snaps_down_to_scale_grid(self, con: Converter) -> None:
        assert con.baseNprice == (1_000_000 // con.scale) * con.scale

    def test_base_timestamp_snaps_down_to_timeframe_boundary(
        self, con: Converter
    ) -> None:
        assert con.baseTimestamp % con.tims == 0
        assert con.baseTimestamp <= 1_700_000_400_000

    def test_center_is_half_of_fp_rows(self, con: Converter) -> None:
        assert con.center == con.fp_rows // 2

    def test_re_calibrating_session_does_not_reset_first_base_timestamp(
        self, con: Converter
    ) -> None:
        first = con._first_base_timestamp
        con.init_session(
            nPrice=np.int64(10_500_00), timestamp=np.int64(1_700_003_000_000)
        )
        assert con._first_base_timestamp == first


class TestToIdy:
    def test_price_at_base_maps_to_center_row(self, con: Converter) -> None:
        assert con.to_idy(con.baseNprice) == con.center

    def test_price_above_base_maps_to_lower_row_index(
        self, con: Converter
    ) -> None:
        higher_price = con.baseNprice + con.scale
        idy = con.to_idy(higher_price)
        assert idy == con.center - 1

    def test_price_below_base_maps_to_higher_row_index(
        self, con: Converter
    ) -> None:
        lower_price = con.baseNprice - con.scale
        idy = con.to_idy(lower_price)
        assert idy == con.center + 1

    def test_out_of_bounds_price_returns_none_both_sides(
        self, con: Converter
    ) -> None:
        # Below bounds (idy >= fp_rows)
        extreme_low = con.baseNprice - (con.fp_rows * con.scale)
        assert con.to_idy(extreme_low) is None
        # Above bounds (idy < 0)
        extreme_high = con.baseNprice + (con.fp_rows * con.scale)
        assert con.to_idy(extreme_high) is None


class TestToIdx:
    def test_at_base_timestamp_buy_side_is_odd_index(
        self, con: Converter
    ) -> None:
        idx = con.to_idx(con.baseTimestamp, is_sell=np.int64(0))
        assert idx == 1

    def test_at_base_timestamp_sell_side_is_even_index(
        self, con: Converter
    ) -> None:
        idx = con.to_idx(con.baseTimestamp, is_sell=np.int64(1))
        assert idx == 0

    def test_next_bar_advances_index_by_two(self, con: Converter) -> None:
        next_bar_ts = con.baseTimestamp + con.tims
        idx_buy = con.to_idx(next_bar_ts, is_sell=np.int64(0))
        assert idx_buy == 3

    def test_out_of_bounds_timestamp_returns_none_both_sides(
        self, con: Converter
    ) -> None:
        # Future bounds (idx >= fp_cols)
        far_future = con.baseTimestamp + (con.fp_cols * con.tims)
        assert con.to_idx(far_future, is_sell=np.int64(0)) is None
        # Past bounds (idx < 0)
        far_past = con.baseTimestamp - con.tims
        assert con.to_idx(far_past, is_sell=np.int64(0)) is None


class TestPriceQtyRoundTrip:
    def test_to_nprice_from_int_and_np_int64(self, con: Converter) -> None:
        price_at_center = con.to_nPrice(int(con.center))
        assert price_at_center == con.baseNprice
        price_at_center_np = con.to_nPrice(np.int64(con.center))
        assert price_at_center_np == con.baseNprice

    def test_to_nqty_from_float_then_back_to_qty(self, con: Converter) -> None:
        n_qty = con.to_nQty(0.25)
        assert n_qty == round(0.25 * con.qty_mult)
        assert con.to_qty(n_qty) == pytest.approx(0.25)

    def test_idy_and_nprice_are_inverse_within_one_scale_step(
        self, con: Converter
    ) -> None:
        original_price = con.baseNprice + (3 * con.scale)
        idy = con.to_idy(original_price)
        assert idy is not None
        recovered_price = con.to_nPrice(idy)
        assert recovered_price == original_price


class TestTimeFormatting:
    def test_to_strftime_formats_as_iso_date(self, con: Converter) -> None:
        assert con.to_strftime(1_700_000_000_000) == "2023-11-14"

    def test_get_time_without_strftime_returns_bar_boundary_timestamp(
        self, con: Converter
    ) -> None:
        idx = con.to_idx(con.baseTimestamp, is_sell=np.int64(0))
        assert idx is not None
        assert con.get_time(idx, strftime=False) == con.baseTimestamp

    def test_get_time_with_strftime_returns_string(
        self, con: Converter
    ) -> None:
        idx = con.to_idx(con.baseTimestamp, is_sell=np.int64(0))
        assert idx is not None
        result = con.get_time(idx, strftime=True)
        assert isinstance(result, str)


class TestGetPrice:
    def test_get_price_rounds_to_coin_price_precision(
        self, con: Converter
    ) -> None:
        price = con.get_price(con.center)
        assert price == round(price, con.price_prec)
        assert price == pytest.approx(
            con.to_price(con.baseNprice),
            abs=10 ** (-con.price_prec),
        )
