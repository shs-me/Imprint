import pytest
from msgspec import ValidationError

import imprint._core.configs as cfg
from imprint._core.settings import Timeframe


def test_validated_struct() -> None:
    """Verify that ValidatedStruct correctly validates and re-converts instances on initialization."""

    class CustomValidated(cfg.ValidatedStruct):
        val: int

    with pytest.raises(ValidationError):
        CustomValidated(val="invalid-int")  # pyright: ignore[reportArgumentType]

    CustomValidated(1)


@pytest.mark.parametrize("pct", [100.0, 1.5, 0.0, 0.05, 0.01, 1e-4])
def test_percent_calculation(pct: float) -> None:
    """Verify manual fixed-point percent calculation across fractional, integer, and edge-case values."""
    expected_fixed = round(pct / 100 * cfg.PERCENT)
    percent = cfg.Percent(pct)
    assert percent.fixed == expected_fixed, (
        f"Expected percent fixed value {expected_fixed} for {pct}%, got {percent.fixed}"
    )


def test_account_scale_mult() -> None:
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
    tick_size: str, lot_size: str, exp_price_prec: int, exp_qty_prec: int
) -> None:
    """Verify Coin precision parsing and derived multiplier calculations across fractions, integers, and scientific notations."""
    coin = cfg.Coin(symbol="TESTUSDT", tick_size=tick_size, lot_size=lot_size)

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


def test_footprint_bar_count_and_columns() -> None:
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
