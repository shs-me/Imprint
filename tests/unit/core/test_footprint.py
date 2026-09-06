"""Unit tests for `imprint.core.footprint` models and JIT engine kernels."""

from typing import override
from unittest.mock import MagicMock

import numpy as np

from imprint.core import constant as c
from imprint.core.footprint.engine.reader import (
    _update_clusters_states,
    calc_value_area,
)
from imprint.core.footprint.engine.router import SyncWithExecution
from imprint.core.footprint.engine.writer import (
    BHM_ConstantCount,
    FU_ConstantCount,
    _update,
)
from imprint.core.footprint.models.base import FPArray


class TestFPArray:
    def test_initialization_and_zero_fill(self) -> None:
        arr = FPArray(rows=10, cols=5)
        assert arr.shape == (10, 5)
        assert np.all(arr == 0)

    def test_padding_adds_rows_correctly(self) -> None:
        arr = FPArray(rows=4, cols=2)
        arr[0, 0] = 42
        padded = arr.padding(before=2, after=3)
        assert padded.shape == (9, 2)
        assert padded[2, 0] == 42
        assert isinstance(padded, FPArray)


class TestValueAreaJitKernel:
    def test_calc_value_area_70_percent(self) -> None:
        # Symmetrical distribution centered at index 5
        vp_slice = np.array(
            [5, 10, 20, 50, 100, 200, 100, 50, 20, 10, 5], dtype=np.int64
        )
        center_idx = np.argmax(vp_slice)  # 5 (val 200)

        vah_idx, val_idx = calc_value_area(vp_slice, center_idx)
        total_vol = np.sum(vp_slice)
        covered_vol = np.sum(vp_slice[vah_idx : val_idx + 1])

        assert covered_vol >= (total_vol * 0.70)
        assert vah_idx <= center_idx <= val_idx


class TestWriterJitKernel:
    def test_update_accumulates_volume_and_updates_headers(self) -> None:
        # 10 rows, 4 cols (col 0: bid, 1: ask, 2: idxVP, 3: idxDP)
        footprint = np.zeros((10, 4), dtype=np.int64)
        headers = np.zeros((2, c.BH_ConstantCount), dtype=np.int64)
        headers_offset = memoryview(bytearray(8)).cast("q")
        bbox = np.array([10, 4, 0, 0], dtype=np.int64)
        meta_data = np.zeros((2, BHM_ConstantCount), dtype=np.float64)

        args = np.zeros((FU_ConstantCount,), dtype=np.int64)
        args[0] = 2  # idxVP
        args[1] = 3  # idxDP
        args[2] = 100  # price_mult
        args[3] = 2  # price_prec
        args[4] = 1000  # qty_mult
        args[5] = 3  # qty_prec

        # Feed a buy tick: price=100.00 (10000), qty=1.0 (1000), sell=0
        _update(
            nPrice=np.int64(10_000),
            nQty=np.int64(1_000),
            timestamp=np.int64(1_700_000_000_000),
            is_sell=np.int64(0),
            idy=np.int64(5),
            idx=np.int64(1),  # Buy col
            args=args,
            footprint=footprint,
            headers=headers,
            headers_offset=headers_offset,
            bbox=bbox,
            meta_data=meta_data,
        )

        assert footprint[5, 1] == 1_000  # In-bar volume
        assert footprint[5, 2] == 1_000  # Volume profile (VP)
        assert footprint[5, 3] == 1_000  # Delta profile (DP)
        assert headers[0, c.BH_Volume] == 1_000
        assert headers[0, c.BH_High] == 10_000
        assert headers[0, c.BH_Low] == 10_000
        assert headers[0, c.BH_Close] == 10_000


class TestReaderStatesJitKernels:
    def test_update_clusters_states_flags_delta_domination(self) -> None:
        fp = np.zeros((4, 4), dtype=np.int64)
        fp_state = np.zeros((4, 4), dtype=np.int32)
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


class DummySync(SyncWithExecution):
    @override
    def sync_with_execution(self) -> None: ...


class TestSyncWithExecution:
    def test_send_signal_packs_data_into_ring_buffer(self) -> None:
        manager = MagicMock()
        manager.cfgMetrics.time_start_reading.view.cast.return_value = (
            memoryview(bytearray(8)).cast("q")
        )
        manager.cfgRiskManagement.pass_signal_if_analysis_time_big = 10_000

        # Create memory buffer for Signal
        sig_data = memoryview(bytearray(100 * 32)).cast("q")
        sig_wid = memoryview(bytearray(8)).cast("q")
        sig_rid = memoryview(bytearray(8)).cast("q")

        manager.cfgSignal.cell_amount = 100
        manager.cfgSignal.safe_lag = 90
        manager.cfgSignal.data_size = 32
        manager.cfgSignal.data.view.cast.return_value = sig_data
        manager.cfgSignal.writer_id.view.cast.return_value = sig_wid
        manager.cfgSignal.reader_id.view.cast.return_value = sig_rid

        sync = DummySync(manager)

        sid = sync.send_signal(
            nPrice=50_000,
            timestamp=1_700_000_000_000,
            is_long=True,
            is_buy=True,
            is_market=True,
            pass_lag=True,
        )

        assert sid == 1
        assert sig_wid[0] == 1
        assert sig_data[0] == 1  # sid
        assert sig_data[1] == 50_000
        assert sig_data[2] == 1_700_000_000_000
        assert sig_data[3] & c.OF_LONG
        assert sig_data[3] & c.OF_BUY
        assert sig_data[3] & c.OF_MARKET
