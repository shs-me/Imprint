"""Footprint analysis reader and JIT state management routines."""

from abc import ABC, abstractmethod

import numpy as np
from numba import njit
from numpy import bool_, int32, int64, intp
from numpy.typing import NDArray

from ... import constant as c
from ...settings import SpaceCoords as sc
from ...utils.monitoring.agent_manager import AgentManager
from .base_sync import Sync
from .utils.fp_con import FPconverter


class FootprintReader(ABC):
    """Base class providing interface for Footprint grid analysis and pattern recognition.

    Attributes:
        fp (NDArray[int64]): Shared 2D Footprint cell volume profile grid.
        fp_state (NDArray[int32]): 2D Footprint cell state bitmask array.
        headers (NDArray[int64]): 2D Bar headers array.
        con (FPconverter): Footprint layout coordinate converter.
    """

    def __init__(
        self,
        manager: AgentManager,
        sync: Sync,
        find_patterns_in_update_bar: bool = False,
        find_patterns_in_update_closed_bar: bool = False,
        find_patterns_in_update_clusters: bool = False,
    ) -> None:
        """Binds memory views, initializes array structures, and instantiates converter."""

        self._manager: AgentManager = manager
        self._sync: Sync = sync
        self._fpiu_bar: bool = find_patterns_in_update_bar
        self._fpiu_closed_bar: bool = find_patterns_in_update_closed_bar
        self._fpiu_clusters: bool = find_patterns_in_update_clusters

        cfgFP = manager.cfgFootprint
        self._space_flag: memoryview = cfgFP.space_flag
        self._spare_flag: memoryview = cfgFP.spare_flag
        self._base_nPrice: memoryview = cfgFP.base_price.cast("q")
        self._base_timestamp: memoryview = cfgFP.base_timestamp.cast("q")

        cfgMetrics = manager.cfgMetrics
        self._trade_readed_time: memoryview = cfgMetrics.trade_readed_time.cast("q")
        self._init_array()
        self.con: FPconverter = FPconverter(
            cfgFP=cfgFP,
            footprint=self.fp,
            headers=self.headers,
            price_prec=manager.cfgCoin.price_prec,
            qty_prec=manager.cfgCoin.qty_prec,
        )

        self._default_space: list[int] = [self.con.fp_rows, self.con.fp_cols, 0, 0]
        self.amRow: int = 0

    def _init_array(self) -> None:
        """Initializes NumPy wrappers around shared memory Footprint, Header, and Space buffers."""

        cfgFP = self._manager.cfgFootprint
        self.fp: NDArray[int64] = np.ndarray(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols),
            dtype=int64,
            buffer=cfgFP.footprint,
        )
        self.fp_state: NDArray[int32] = np.zeros(
            shape=(cfgFP.fp_rows, cfgFP.fp_panel_cols), dtype=int32
        )
        self.headers: NDArray[int64] = np.ndarray(
            shape=(cfgFP.bar_count, c.BH_ConstantCount),
            dtype=int64,
            buffer=cfgFP.headers,
        )
        self._space: NDArray[int64] = np.ndarray(
            (2, sc._ConstantCount), dtype=int64, buffer=cfgFP.space
        )
        self.algorithm_metadata: NDArray[int64] = np.zeros((2, 2), dtype=int64)
        self.cachedStatesData: NDArray[int32] = np.zeros(
            (c.CSD_ConstantCount,), dtype=int32
        )

    def _init_session(self) -> None:
        """Resets state arrays and calibrates layout converter for a new trading session."""

        self.fp_state.fill(0)
        self.last_idx: int = 0
        self.con.init_session(
            price=self._base_nPrice[0], timestamp=self._base_timestamp[0]
        )

    # Agent/Sync Methods's
    def _final_actions(self) -> None:
        """Persists strategy analytics metadata to disk if configured."""

        if self._manager.cfgFootprint.save_algorithm_metadata:
            np.save(
                c.ALGORITHM_METADATA_DUMP_PATH, self.algorithm_metadata[: self.amRow, :]
            )

    def send_signal(
        self,
        is_market: bool,
        is_long: bool,
        is_buy: bool,
        idy: int64,
        idx: int | None = None,
        timestamp: int | None = None,
        pass_lag: bool = True,
    ) -> None:
        """Dispatches trade signal to Execution pipeline via Sync helper.

        Args:
            is_market (bool): True for Market orders, False for Limit.
            is_long (bool): Position direction (True=Long, False=Short).
            is_buy (bool): Trade action side (True=Buy, False=Sell).
            idy (int64): Price level Y-axis row index.
            idx (int | None): Bar column index.
            timestamp (int | None): Explicit event timestamp in milliseconds.
            pass_lag (bool): Flag to bypass processing latency validation checks.
        """

        nPrice: int = int(self.con.to_nPrice(idy))
        _idx: int = idx if (idx is not None) else self.last_idx
        _ms: int = (
            timestamp if (timestamp is not None) else int(self.con.lastTradeTime(_idx))
        )
        self._sync.send_signal(
            nPrice=nPrice,
            time_ms=_ms,
            is_long=is_long,
            is_buy=is_buy,
            is_market=is_market,
            pass_lag=pass_lag,
        )

    # - - Footprint Analysis/Update Methods - -
    def _update_states(self) -> None:
        """Executes Numba update routines for clusters, closed bars, and active bar state flags."""

        oldBuf: int = 1 if (self._space_flag[0] == 0) else 0
        idYmin, idXmin, idYmax, idXmax = self._space[oldBuf, :]
        self._update_clusters(idYmin, idYmax, idXmin, idXmax)
        for idx in range((idXmin & ~1), idXmax, 2):
            idxBid, idxAsk = idx, idx + 1
            if self.con.volume(idx) > 0:
                if idx > self.last_idx:
                    self._update_closed_bar_and_fp()
                    self._trade_readed_time[0] = int(
                        self.con.lastTradeTime(self.last_idx)
                    )
                    self.last_idx = idx

                self._update_bar(idYmin, idYmax, idxBid, idxAsk)

        self._space[oldBuf, :] = self._default_space

    def _update_clusters(
        self,
        idYmin: int64,
        idYmax: int64,
        idXmin: int64,
        idXmax: int64,
        in_update_clusters: bool = True,
    ) -> None:
        """Invokes cluster-level state updates and pattern recognition callbacks."""

        _update_clusters_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idXmin=idXmin,
            idXmax=idXmax,
            idxVP=self.con.idxVP,
            idxDP=self.con.idxDP,
            fp=self.fp,
            fp_state=self.fp_state,
        )
        if self._fpiu_clusters:
            if in_update_clusters:
                self.find_patterns(in_update_clusters=in_update_clusters)

    def _update_closed_bar_and_fp(
        self,
        in_update_closed_bar: bool = True,
    ) -> None:
        """Invokes closed bar calculation routines and updates static Footprint indicators."""

        _update_closed_bar_and_fp_states(
            lidx=self.last_idx,
            idxVP=self.con.idxVP,
            idxDP=self.con.idxDP,
            hr=self.headers,
            fp=self.fp,
            fp_state=self.fp_state,
            caching=self.cachedStatesData,
            nBasePrice=self.con.nBasePrice,
            center=self.con.center,
        )
        if self._fpiu_closed_bar:
            if in_update_closed_bar:
                self.find_patterns(in_update_closed_bar=in_update_closed_bar)

    def _update_bar(
        self,
        idYmin: int64,
        idYmax: int64,
        idxBid: int,
        idxAsk: int,
        in_update_bar: bool = True,
    ) -> None:
        """Invokes active bar state updates and triggers pattern scanning callbacks."""

        _update_bar_states(
            idYmin=idYmin,
            idYmax=idYmax,
            idxBid=idxBid,
            idxAsk=idxAsk,
            hr=self.headers,
            fp=self.fp,
            fp_state=self.fp_state,
            nBasePrice=self.con.nBasePrice,
            center=self.con.center,
        )
        if self._fpiu_bar:
            if in_update_bar:
                self.find_patterns(in_update_bar=in_update_bar)

    @abstractmethod
    def find_patterns(
        self,
        in_update_bar: bool = False,
        in_update_closed_bar: bool = False,
        in_update_clusters: bool = False,
    ) -> None:
        """Abstract pattern detection entry point overridden by user strategy implementations.

        Args:
            in_update_bar (bool): True if invoked during active bar tick updates.
            in_update_closed_bar (bool): True if invoked upon bar closure.
            in_update_clusters (bool): True if invoked during cluster-level volume updates.
        """

        pass

    def bar_state_mask(self, idxBid: int) -> NDArray[int32]:
        """Returns bitmask slice of active bar indicator flags.

        Args:
            idxBid (int): Bar Bid column index.

        Returns:
            NDArray[int32]: Sliced state bitmask array for the specified bar.
        """

        bar_flags = (
            c.SF_OPEN
            | c.SF_HIGH
            | c.SF_LOW
            | c.SF_CLOSE
            | c.SF_POC_BAR
            | c.SF_VAH_BAR
            | c.SF_VAL_BAR
        )
        bid_ask_flags = (
            c.SF_DELTA_DOMINATION
            | c.SF_IMBALANCE
            | c.SF_ZERO_PRINT
            | c.SF_FINISHED_AUCTION
            | c.SF_UNFINISHED_AUCTION
        )
        mask = bar_flags | bid_ask_flags
        idYmin: int64 = self.con.to_idy(self.con.highNprice(idxBid))
        idyMax: int64 = self.con.to_idy(self.con.lowNprice(idxBid))
        return self.fp_state[idYmin : idyMax + 1, idxBid : idxBid + 2] & mask

    def fp_state_mask(self, idYmin: int64, idYmax: int64) -> NDArray[int32]:
        """Returns bitmask slice of auction completion flags for specified row bounds."""

        state = c.SF_FINISHED_AUCTION | c.SF_UNFINISHED_AUCTION
        return self.fp_state[idYmin:idYmax, self.con.idxVP] & state


class BaseFootprintReader(FootprintReader):
    """Default no-op implementation of FootprintReader."""

    def __init__(self, manager: AgentManager, sync: Sync) -> None:
        super().__init__(manager, sync)

    def find_patterns(
        self,
        in_update_bar: bool = False,
        in_update_closed_bar: bool = False,
        in_update_clusters: bool = False,
    ) -> None:
        pass


@njit(cache=True)
def _update_clusters_states(
    idYmin: int64,
    idYmax: int64,
    idXmin: int64,
    idXmax: int64,
    idxVP: int,
    idxDP: int,
    fp: NDArray[int64],
    fp_state: NDArray[int32],
) -> None:
    """Numba JIT kernel recalculating delta domination and big trade flags across clusters."""

    # - - -
    # Clear State's
    fp_state[idYmin:idYmax, idXmin:idXmax] &= ~(c.SF_BIG_TRADE)
    # - - -
    # Clear State's
    state1 = c.SF_BID_DELTA_DOMINATION_FP | c.SF_ASK_DELTA_DOMINATION_FP
    fp_state[idYmin:idYmax, idxVP] &= ~(state1)
    # Update Delta Domination
    bidDD: NDArray[bool_] = fp[idYmin:idYmax, idxDP] < 0
    askDD: NDArray[bool_] = fp[idYmin:idYmax, idxDP] > 0
    fp_state[idYmin:idYmax, idxVP][bidDD] |= c.SF_BID_DELTA_DOMINATION_FP
    fp_state[idYmin:idYmax, idxVP][askDD] |= c.SF_ASK_DELTA_DOMINATION_FP


@njit(cache=True)
def _update_closed_bar_and_fp_states(
    lidx: int,
    idxVP: int,
    idxDP: int,
    hr: NDArray[int64],
    fp: NDArray[int64],
    fp_state: NDArray[int32],
    caching: NDArray[int32],
    nBasePrice: int,
    center: int,
) -> None:
    """Numba JIT kernel calculating ATR, VWAP, Bollinger Bands, POC, and Value Area on bar closure."""

    bar: int = (lidx & ~1) // 2
    oldBar: int = bar - 1
    _open: int64 = hr[bar, c.BH_Open]
    _high: int64 = hr[bar, c.BH_High]
    _low: int64 = hr[bar, c.BH_Low]
    _close: int64 = hr[bar, c.BH_Close]
    _openY, _closeY = (nBasePrice - _open) + center, (nBasePrice - _close) + center
    _highY, _lowY = (nBasePrice - _high) + center, (nBasePrice - _low) + center
    # - - -
    # ATR
    if bar > 0:
        pre_c, pre_atr = hr[oldBar, c.BH_Close], hr[oldBar, c.BH_ATR]
        tr = max(_high - _low, abs(_high - pre_c), abs(_low - pre_c))
        hr[bar, c.BH_ATR] = ((pre_atr * (c.ATR_PERIOD - 1)) + tr) // c.ATR_PERIOD
    else:
        hr[bar, c.BH_ATR] = _high - _low

    # Clear Footprint Static State's
    state_1 = c.SF_VWAP | c.SF_LOWER_BB | c.SF_UPPER_BB
    state_2 = c.SF_POC_BAR | c.SF_VAL_FP | c.SF_VAH_FP
    state_3 = c.SF_UNFINISHED_AUCTION | c.SF_FINISHED_AUCTION
    fp_state[caching[c.CSD_VWAP : c.CSD_LOWER_BB + 1], idxVP] &= ~(state_1)
    fp_state[caching[c.CSD_POC_FP : c.CSD_VAL_FP + 1], idxVP] &= ~(state_2)
    fp_state[_highY : _lowY + 1, idxVP] &= ~(state_3)
    # Update VWAP+BB
    vwap = (nBasePrice - hr[bar, c.BH_VWAP]) + center
    vwap_bb_lower = (nBasePrice - hr[bar, c.BH_VWAP_BB_LOWER]) + center
    vwap_bb_upper = (nBasePrice - hr[bar, c.BH_VWAP_BB_UPPER]) + center
    if 0 <= vwap < fp_state.shape[0]:
        fp_state[vwap, idxVP] |= c.SF_VWAP
    if 0 <= vwap_bb_upper < fp_state.shape[0]:
        fp_state[vwap_bb_upper, idxVP] |= c.SF_UPPER_BB
    if 0 <= vwap_bb_lower < fp_state.shape[0]:
        fp_state[vwap_bb_lower, idxVP] |= c.SF_LOWER_BB
    # Update POC + VA
    poc: intp = np.argmax(fp[:, idxVP])
    vah, val = calc_value_area(vp_slice=fp[:, idxVP], center_idx=poc)
    fp_state[poc, idxVP] |= c.SF_POC_FP
    fp_state[vah, idxVP] |= c.SF_VAH_FP
    fp_state[val, idxVP] |= c.SF_VAL_FP
    # Update Auction
    highAuction = (
        c.SF_FINISHED_AUCTION if fp[_highY, lidx + 1] == 0 else c.SF_UNFINISHED_AUCTION
    )
    lowAuction = (
        c.SF_FINISHED_AUCTION if fp[_lowY, lidx] == 0 else c.SF_UNFINISHED_AUCTION
    )
    fp_state[_highY, idxVP] |= highAuction
    fp_state[_lowY, idxVP] |= lowAuction
    # Caching
    caching[c.CSD_VWAP] = vwap
    caching[c.CSD_UPPER_BB] = vwap_bb_upper
    caching[c.CSD_LOWER_BB] = vwap_bb_lower
    caching[c.CSD_POC_FP] = poc
    caching[c.CSD_VAH_FP] = vah
    caching[c.CSD_VAL_FP] = val


@njit(cache=True)
def _update_bar_states(
    idYmin: int64,
    idYmax: int64,
    idxBid: int,
    idxAsk: int,
    hr: NDArray[int64],
    fp: NDArray[int64],
    fp_state: NDArray[int32],
    nBasePrice: int,
    center: int,
) -> None:
    """Numba JIT kernel calculating active bar OHLC, Zero-Print, Delta Domination, and Imbalances."""

    bar = (idxBid & ~1) // 2
    _open: int64 = hr[bar, c.BH_Open]
    _high: int64 = hr[bar, c.BH_High]
    _low: int64 = hr[bar, c.BH_Low]
    _close: int64 = hr[bar, c.BH_Close]
    _openY, _closeY = (nBasePrice - _open) + center, (nBasePrice - _close) + center
    _highY, _lowY = (nBasePrice - _high) + center, (nBasePrice - _low) + center

    # - - -
    idyBid: slice[int64, int64] = slice(idYmin + 1, idYmax + 1)
    idyAsk: slice[int64, int64] = slice(idYmin, idYmax)
    # Clear State's
    indicators = c.SF_ZERO_PRINT | c.SF_DELTA_DOMINATION | c.SF_IMBALANCE
    clear_mask = ~(indicators)
    fp_state[idYmin : idYmax + 1, idxBid : idxBid + 2] &= clear_mask
    # Update ZeroPrint
    bidZP: NDArray[bool_] = (fp[idyAsk, idxAsk] > 0) & (fp[idyBid, idxBid] == 0)
    askZP: NDArray[bool_] = (fp[idyBid, idxBid] > 0) & (fp[idyAsk, idxAsk] == 0)
    fp_state[idyBid, idxBid][bidZP] |= c.SF_ZERO_PRINT
    fp_state[idyAsk, idxAsk][askZP] |= c.SF_ZERO_PRINT
    # Update Delta Domination
    bidDD: NDArray[bool_] = (fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) < 0
    askDD: NDArray[bool_] = (fp[idyBid, idxBid] - fp[idyAsk, idxAsk]) > 0
    fp_state[idyBid, idxBid][bidDD] |= c.SF_DELTA_DOMINATION
    fp_state[idyAsk, idxAsk][askDD] |= c.SF_DELTA_DOMINATION
    # Update IMBALANCE
    bidImb: NDArray[bool_] = fp[idyBid, idxBid] > (fp[idyAsk, idxAsk] * 3)
    askImb: NDArray[bool_] = fp[idyAsk, idxAsk] > (fp[idyBid, idxBid] * 3)
    fp_state[idyBid, idxBid][bidImb] |= c.SF_IMBALANCE
    fp_state[idyAsk, idxAsk][askImb] |= c.SF_IMBALANCE

    # - - -
    # Clear State's
    headers = c.SF_OPEN | c.SF_HIGH | c.SF_LOW | c.SF_CLOSE
    indicators = c.SF_POC_BAR | c.SF_VAL_BAR | c.SF_VAH_BAR
    clear_mask = ~(headers | indicators)
    fp_state[_highY : _lowY + 1, idxBid] &= clear_mask
    # Update OHLC
    fp_state[_openY, idxBid] |= c.SF_OPEN
    fp_state[_highY, idxBid] |= c.SF_HIGH
    fp_state[_lowY, idxBid] |= c.SF_LOW
    fp_state[_closeY, idxBid] |= c.SF_CLOSE
    # Update VA + POC
    vp_bar: NDArray[int64] = (
        fp[_highY : _lowY + 1, idxBid] + fp[_highY : _lowY + 1, idxAsk]
    )
    poc: intp = np.argmax(vp_bar)
    vah, val = calc_value_area(vp_slice=vp_bar, center_idx=poc)
    hr[bar, c.BH_POC] = poc = _highY + poc
    hr[bar, c.BH_VAH] = vah = _highY + vah
    hr[bar, c.BH_VAL] = val = _highY + val
    fp_state[poc, idxBid] |= c.SF_POC_BAR
    fp_state[vah, idxBid] |= c.SF_VAH_BAR
    fp_state[val, idxBid] |= c.SF_VAL_BAR


@njit(cache=True)
def calc_value_area(vp_slice: NDArray[int64], center_idx: intp) -> tuple[intp, intp]:
    """Numba JIT kernel computing Value Area High (VAH) and Low (VAL) covering 70% of volume profile."""

    target_vol: float = np.sum(vp_slice) * 0.70
    current_vol: int64 = vp_slice[center_idx]
    max_len: int = len(vp_slice)
    up_idx: intp = center_idx - 1
    down_idx: intp = center_idx + 1
    while current_vol < target_vol:
        if 0 <= up_idx or down_idx < max_len:
            vol_up = vp_slice[up_idx] if 0 <= up_idx else 0
            vol_down = vp_slice[down_idx] if down_idx < max_len else 0
            if vol_up > vol_down:
                up_idx -= 1
                current_vol += vol_up

            elif vol_down > vol_up:
                down_idx += 1
                current_vol += vol_down

            elif vol_up == vol_down:
                if up_idx >= 0:
                    up_idx -= 1
                    current_vol += vol_up

                if down_idx < max_len:
                    down_idx += 1
                    current_vol += vol_down
        else:
            break

    return up_idx + 1, down_idx - 1
