"""Unit tests for `imprint.core.exchange.account.manager`."""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from imprint._core import constant as c
from imprint._core.configs import Account, Coin, Footprint, Setup
from imprint._core.exchange_sim.account.manager import (
    EquityC,
    EquityH,
    EquityL,
    EquityO,
    EquityT,
    Manager,
    update_equity_ohlc,
)
from imprint._core.settings import Timeframe


class ConcreteManager(Manager):
    """Concrete subclass of Manager for testing."""


def _make_node_manager(
    start_date: str = "2026-01-01",
    end_date: str = "2026-01-03",
    timeframe: Timeframe = Timeframe.M5,
    latency_ms: int = 150,
) -> MagicMock:
    mgr = MagicMock()
    mgr.cfgCoin = Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")
    mgr.cfgAccount = Account(
        leverage=10,
        balance=1_000.0,
        latency_ms=latency_ms,
        scale_prec=8,
    )
    mgr.cfgFootprint = Footprint(timeframe=timeframe)
    mgr.cfgSetup = Setup(
        backtest_start_date=start_date, backtest_end_date=end_date
    )
    return mgr


class TestEquityConstants:
    def test_equity_index_constants(self) -> None:
        assert EquityT == 0
        assert EquityO == 1
        assert EquityH == 2
        assert EquityL == 3
        assert EquityC == 4


class TestManagerClass:
    def test_manager_multi_day_bar_count(self) -> None:
        # 3 days: Jan 1, Jan 2, Jan 3 -> 3 * 86_400_000 ms // 300_000 ms (M5) = 864 bars
        mgr_mock = _make_node_manager(
            start_date="2026-01-01",
            end_date="2026-01-03",
            timeframe=Timeframe.M5,
        )
        manager = ConcreteManager(manager=mgr_mock)

        assert manager.latency == 150
        assert manager.timeframe == int(Timeframe.M5)
        assert manager.bar_count == 864
        assert manager.equity_history.shape == (864, 5)
        assert manager.base_timestamp[0] == 0

    def test_manager_single_day_bar_count(self) -> None:
        # 1 day -> 86_400_000 // 3_600_000 (H1) = 24 bars
        mgr_mock = _make_node_manager(
            start_date="2026-01-01",
            end_date="2026-01-01",
            timeframe=Timeframe.H1,
        )
        manager = ConcreteManager(manager=mgr_mock)

        assert manager.bar_count == 24
        assert manager.equity_history.shape == (24, 5)

    def test_manager_inverted_dates_clamps_to_one_day(self) -> None:
        # end_date before start_date -> max(1, negative) = 1 day
        mgr_mock = _make_node_manager(
            start_date="2026-01-05",
            end_date="2026-01-01",
            timeframe=Timeframe.H1,
        )
        manager = ConcreteManager(manager=mgr_mock)

        assert manager.bar_count == 24

    def test_dump_equity_history_and_final_action(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_dest = tmp_path / "equity_history.npy"
        monkeypatch.setattr(c, "EQUITY_HISTORY_DUMP_PATH", str(save_dest))

        mgr_mock = _make_node_manager(
            start_date="2026-01-01", end_date="2026-01-01"
        )
        manager = ConcreteManager(manager=mgr_mock)

        # Populate two valid bars and leave the rest as 0
        manager.equity_history[0, :] = [1_700_000_000_000, 100, 110, 90, 105]
        manager.equity_history[1, :] = [1_700_000_300_000, 105, 120, 100, 115]

        manager.final_action()

        assert save_dest.exists()
        saved = np.load(str(save_dest))
        assert saved.shape == (2, 5)
        assert saved[0, EquityT] == 1_700_000_000_000
        assert saved[1, EquityC] == 115


class TestUpdateEquityOhlc:
    def test_initial_bar_creation(self) -> None:
        eh = np.zeros((10, 5), dtype=np.int64)
        base_ts = memoryview(bytearray(8)).cast("q")
        timeframe = 300_000  # 5 min

        trade_ts = 1_700_000_123_456
        current_eq = 10_000

        update_equity_ohlc(trade_ts, current_eq, eh, base_ts, timeframe)

        expected_base = trade_ts - (trade_ts % timeframe)
        assert base_ts[0] == expected_base
        assert eh[0, EquityT] == expected_base
        assert eh[0, EquityO] == current_eq
        assert eh[0, EquityH] == current_eq
        assert eh[0, EquityL] == current_eq
        assert eh[0, EquityC] == current_eq

    def test_update_current_bar_high_low_close(self) -> None:
        eh = np.zeros((10, 5), dtype=np.int64)
        base_ts = memoryview(bytearray(8)).cast("q")
        timeframe = 300_000
        trade_ts = 1_700_000_000_000

        # Bar 0 opened at 10_000
        update_equity_ohlc(trade_ts, 10_000, eh, base_ts, timeframe)

        # 1. Equity moves higher -> High and Close updated
        update_equity_ohlc(trade_ts + 1_000, 12_000, eh, base_ts, timeframe)
        assert eh[0, EquityO] == 10_000
        assert eh[0, EquityH] == 12_000
        assert eh[0, EquityL] == 10_000
        assert eh[0, EquityC] == 12_000

        # 2. Equity drops lower -> Low and Close updated
        update_equity_ohlc(trade_ts + 2_000, 8_000, eh, base_ts, timeframe)
        assert eh[0, EquityH] == 12_000
        assert eh[0, EquityL] == 8_000
        assert eh[0, EquityC] == 8_000

        # 3. Intermediate move -> only Close updated
        update_equity_ohlc(trade_ts + 3_000, 9_500, eh, base_ts, timeframe)
        assert eh[0, EquityH] == 12_000
        assert eh[0, EquityL] == 8_000
        assert eh[0, EquityC] == 9_500

    def test_next_consecutive_bar(self) -> None:
        eh = np.zeros((10, 5), dtype=np.int64)
        base_ts = memoryview(bytearray(8)).cast("q")
        timeframe = 300_000
        trade_ts = 1_700_000_000_000

        # Bar 0
        update_equity_ohlc(trade_ts, 10_000, eh, base_ts, timeframe)
        # Next bar (Bar 1)
        update_equity_ohlc(trade_ts + timeframe, 10_500, eh, base_ts, timeframe)

        assert eh[1, EquityT] == base_ts[0] + timeframe
        assert eh[1, EquityO] == 10_500
        assert eh[1, EquityH] == 10_500
        assert eh[1, EquityL] == 10_500
        assert eh[1, EquityC] == 10_500

    def test_gap_filling_multiple_bars(self) -> None:
        eh = np.zeros((10, 5), dtype=np.int64)
        base_ts = memoryview(bytearray(8)).cast("q")
        timeframe = 300_000
        trade_ts = 1_700_000_000_000

        # Bar 0 closed at 10_000
        update_equity_ohlc(trade_ts, 10_000, eh, base_ts, timeframe)

        # Jump directly to Bar 3 (skipping Bar 1 and Bar 2)
        jump_ts = trade_ts + (3 * timeframe)
        update_equity_ohlc(jump_ts, 11_000, eh, base_ts, timeframe)

        # Verify Bar 1 and Bar 2 were forward-filled with previous Close (10_000)
        for missing_bar in (1, 2):
            expected_time = base_ts[0] + (missing_bar * timeframe)
            assert eh[missing_bar, EquityT] == expected_time
            assert eh[missing_bar, EquityO] == 10_000
            assert eh[missing_bar, EquityH] == 10_000
            assert eh[missing_bar, EquityL] == 10_000
            assert eh[missing_bar, EquityC] == 10_000

        # Verify Bar 3 has the new equity value
        assert eh[3, EquityT] == base_ts[0] + (3 * timeframe)
        assert eh[3, EquityO] == 11_000
        assert eh[3, EquityC] == 11_000

    def test_gap_when_no_prior_bars_exist(self) -> None:
        # Edge case: base_timestamp was manually seeded, but first trade lands on Bar 2
        eh = np.zeros((10, 5), dtype=np.int64)
        base_ts = memoryview(bytearray(8)).cast("q")
        timeframe = 300_000
        base_ts[0] = 1_700_000_000_000

        trade_ts = base_ts[0] + (2 * timeframe)
        update_equity_ohlc(trade_ts, 15_000, eh, base_ts, timeframe)

        # Bar 2 is created
        assert eh[2, EquityT] == trade_ts
        assert eh[2, EquityC] == 15_000
        # Bars 0 and 1 remain empty because prev_bar reaches -1
        assert eh[0, EquityT] == 0
        assert eh[1, EquityT] == 0

    def test_out_of_bounds_bars_ignored(self) -> None:
        eh = np.zeros((5, 5), dtype=np.int64)
        base_ts = memoryview(bytearray(8)).cast("q")
        timeframe = 300_000
        base_ts[0] = 1_700_000_000_000

        # 1. Past trade (bar < 0)
        past_ts = base_ts[0] - timeframe
        update_equity_ohlc(past_ts, 9_000, eh, base_ts, timeframe)
        assert np.all(eh == 0)

        # 2. Future trade beyond array capacity (bar >= max_bars = 5)
        future_ts = base_ts[0] + (10 * timeframe)
        update_equity_ohlc(future_ts, 20_000, eh, base_ts, timeframe)
        assert np.all(eh == 0)
