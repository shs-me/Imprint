from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import final

import numba as nb
import numpy as np
from numba import types  # pyright: ignore[reportPrivateImportUsage]
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.footprint.models import Converter, Footprint
from imprint._core.ipc import NodeManager
from imprint._core.settings import StatusCodes as scs
from imprint._core.types import AlgorithmProtocol
from imprint._core.utils import FPArray


@dataclass(slots=True)
class Base(ABC):
    """Abstract base engine managing footprint calculations, sessions, and state arrays.

    Parameters
    ----------
    manager : NodeManager
        Coordinator managing inter-process communication, configuration states,
        and process status codes.
    algorithm : AlgorithmProtocol
        Trading or calculation algorithm execution protocol attached to the engine.

    Attributes
    ----------
    manager : NodeManager
        Coordinator managing inter-process communication, configuration states,
        and process status codes.
    algorithm : AlgorithmProtocol
        Trading or calculation algorithm execution protocol attached to the engine.
    re_init : int
        Bitmask governing re-initialization flags (session, index, and array states).
    trade_read_time : memoryview
        Memory view pointing to trade read timing metrics cast to 64-bit signed integers.
    idYmin : memoryview
        Memory view storing the minimum valid price row index bounded as a 64-bit signed integer.
    idYmax : memoryview
        Memory view storing the maximum valid price row index bounded as a 64-bit signed integer.
    idx : memoryview
        Memory view pointing to the current active bar index as a 64-bit signed integer.
    lidx : memoryview
        Memory view pointing to the last processed bar index as a 64-bit signed integer.
    fp : Footprint
        Core footprint data container wrapping price, volume, state, and trade arrays.
    with_state : bool
        Flag indicating whether state tracking is enabled in footprint configuration.
    with_ctrade : bool
        Flag indicating whether cumulative trade tracking is enabled in footprint configuration.
    storage : JitStorage
        JIT-compiled storage container bridging Python arrays to Numba-compiled scopes.
    """

    manager: NodeManager
    algorithm: AlgorithmProtocol

    __init_arrays: bool = field(default=True, init=False)
    __base_fp_dump_path: str = field(init=False)

    re_init: int = field(default=c.RIF_session | c.RIF_idx, init=False)
    trade_read_time: memoryview = field(init=False)
    idYmin: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    idYmax: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    idx: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    lidx: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    fp: Footprint = field(init=False)
    with_state: bool = field(init=False)
    with_ctrade: bool = field(init=False)
    storage: JitStorage = field(init=False)

    @final
    def __post_init__(self) -> None:
        """Initialize footprint engine configurations, directories, and data structures."""
        cfgFP = self.manager.cfgFootprint
        self.with_state = cfgFP.state
        self.with_ctrade = cfgFP.ctrade

        cfgCoin = self.manager.cfgCoin
        self.__base_fp_dump_path = (
            f"{c.FOOTPRINT_HEADERS_DATA_PATH}/{cfgCoin.symbol.upper()}"
        )

        cfgMetrics = self.manager.cfgMetrics
        self.trade_read_time = cfgMetrics.trade_read_time.view.cast("q")

        cfgSetup = self.manager.cfgSetup
        if cfgSetup.backtesting:
            start_dt: date = date.fromisoformat(cfgSetup.backtest_start_date)
            end_dt: date = date.fromisoformat(cfgSetup.backtest_end_date)
            total_days: int = max(1, (end_dt - start_dt).days + 1)
            self.fp = Footprint(
                Converter(
                    cfgCoin=cfgCoin, cfgFP=cfgFP, total_backtest_days=total_days
                ),
                self.lidx,
            )
        else:
            self.fp = Footprint(
                Converter(cfgCoin=cfgCoin, cfgFP=cfgFP), self.lidx
            )

        self.post_init()

    def post_init(self) -> None: ...

    @final
    def init_session(self, nPrice: int64, timestamp: int64) -> None:
        """Initialize or reset session arrays, indexes, and process status codes.

        Parameters
        ----------
        nPrice : int64
            Number of price levels or normalized price bound for array sizing.
        timestamp : int64
            Unix timestamp in microseconds marking the beginning of the session.
        """
        if self.__init_arrays:
            self.__init_array(nPrice=nPrice)
            self.__init_arrays = False

        if self.re_init & c.RIF_idx:
            self.manager.set_proc_sc(
                code=scs.FP_IDX_FILLED, wait_main_task=False
            )
            self.__init_idx(nPrice, timestamp)
            self.re_init &= ~(c.RIF_idx)

        if self.re_init & c.RIF_idy:
            self.manager.set_proc_sc(
                code=scs.FP_IDY_FILLED, wait_main_task=False
            )
            self.__init_idy(nPrice)
            self.re_init &= ~(c.RIF_idy)

        self.re_init &= ~(c.RIF_session)
        self.manager.set_proc_sc(scs.FP_RE_INIT, wait_main_task=False)

    @final
    def __init_idx(self, nPrice: int64, timestamp: int64) -> None:
        """Reset footprint base, state, and trade arrays, and advance header offsets.

        Parameters
        ----------
        nPrice : int64
            Number of price levels for index reset bounds.
        timestamp : int64
            Unix timestamp in microseconds for session initialization.
        """
        self.fp.base.fill(0)
        if self.with_state:
            self.fp.state.fill(0)
        if self.with_ctrade:
            self.fp.ctrade.fill(0)

        if self.fp.con._first_base_timestamp:
            new_offset = self.fp.headers_offset[0] + (self.fp.con.bar_count)
            if self.fp.headers.shape[0] <= new_offset:
                self.fp.headers_offset[0] = 0
                self.fp.headers.fill(0)
            else:
                self.fp.headers_offset[0] = new_offset

        self.idYmin[0], self.idYmax[0] = self.fp.con.fp_rows[0], 0
        self.idx[0], self.lidx[0] = 0, 0

        self.fp.con.init_session(nPrice=nPrice, timestamp=timestamp)
        self.child_init_idx(nPrice, timestamp)

    @abstractmethod
    def child_init_idx(self, nPrice: int64, timestamp: int64) -> None:
        """Execute child-specific index initialization logic.

        Parameters
        ----------
        nPrice : int64
            Number of price levels for index reset bounds.
        timestamp : int64
            Unix timestamp in microseconds for session initialization.
        """

    @final
    def __init_idy(self, nPrice: int64) -> None:
        """Re-initialize underlying data arrays based on price scaling changes.

        Parameters
        ----------
        nPrice : int64
            Updated number of price levels.
        """
        self.__init_array(nPrice=nPrice)

    @final
    def __init_array(self, nPrice: int64) -> None:
        """Allocate or pad footprint base, state, and cumulative trade arrays.

        Parameters
        ----------
        nPrice : int64
            Number of price levels used to determine row counts and padding bounds.
        """
        con = self.fp.con
        # - - -
        if not (self.re_init & c.RIF_idy):
            con.fp_rows[0] = int(2 * (nPrice * 20 // 100 // con.scale))
            rows, cols = con.fp_rows[0], con.fp_panel_cols
            self.fp._re_init_arr(
                base=FPArray(rows, cols),
                state=(FPArray(rows, cols) if self.with_state else None),
                ctrade=(FPArray(rows, cols) if self.with_ctrade else None),
            )
            self.idYmin[0], self.idYmax[0] = rows, 0
            self.storage = JitStorage(
                headers=self.fp.headers,
                headers_offset=self.fp.headers_offset,
                idYmin=self.idYmin,
                idYmax=self.idYmax,
                idx=self.idx,
                lidx=self.lidx,
                baseTimestamp=con.baseTimestamp,
                baseNprice=con.baseNprice,
                center=con.center,
                fp_rows=con.fp_rows,
                fp_cols=con.fp_cols,
                idxVP=con.idxVP,
                idxDP=con.idxDP,
                tims=con.tims,
                scale=con.scale,
                step_tick=con.step_tick,
                price_mult=con.price_mult,
                price_prec=con.price_prec,
                qty_mult=con.qty_mult,
                qty_prec=con.qty_prec,
                with_state=self.with_state,
                with_ctrade=self.with_ctrade,
            )
        else:
            need_rows: int64 = nPrice * 20 // 100 // con.scale
            con.fp_rows[0] = int(con.fp_rows[0] + need_rows)

            if nPrice > con.baseNprice[0]:
                before, after = need_rows, 0
                con.center[0] = int(con.center[0] + need_rows)
            else:
                before, after = 0, need_rows

            self.fp._re_init_arr(
                base=self.fp.base.padding(int(before), int(after)),
                state=(
                    self.fp.state.padding(int(before), int(after))
                    if self.with_state
                    else None
                ),
                ctrade=(
                    self.fp.ctrade.padding(int(before), int(after))
                    if self.with_ctrade
                    else None
                ),
            )
            self.idYmin[0], self.idYmax[0] = con.fp_rows[0], 0

        self.child_init_array(nPrice)

    @abstractmethod
    def child_init_array(self, nPrice: int64) -> None:
        """Execute child-specific array initialization logic.

        Parameters
        ----------
        nPrice : int64
            Number of price levels.
        """

    @final
    def save_footprint_headers(self, last_idx: int) -> None:
        """Persist footprint headers to disk during backtesting mode.

        Parameters
        ----------
        last_idx : int
            Index of the final bar in the current session range.
        """
        if self.manager.cfgSetup.backtesting:
            os.makedirs(self.__base_fp_dump_path, exist_ok=True)

            start_time: str = self.fp.con.to_strftime(
                self.fp.con._first_base_timestamp
            )
            end_time: str = self.fp.con.get_time(idx=last_idx, strftime=True)

            start_date: date = date.fromisoformat(start_time)
            end_date: date = date.fromisoformat(end_time)

            paths: list[str] = [
                p.split(".npy")[0]
                for p in os.listdir(self.__base_fp_dump_path)
                if p.endswith(".npy")
            ]
            if paths:
                for p in paths:
                    file_timeframe, file_start_time, file_end_time = p.split(
                        "_"
                    )
                    if file_timeframe == self.fp.con.timeframe:
                        file_start_date: date = date.fromisoformat(
                            file_start_time
                        )
                        file_end_date: date = date.fromisoformat(file_end_time)
                        if (
                            file_start_date
                            <= start_date
                            <= end_date
                            <= file_end_date
                        ):
                            return
                        else:
                            os.remove(f"{self.__base_fp_dump_path}/{p}.npy")

            headers_save_path: str = (
                f"{self.__base_fp_dump_path}/"
                f"{self.fp.con.timeframe}"
                f"_{start_time}_{end_time}.npy"
            )
            np.save(headers_save_path, self.fp.headers)


spec = [
    ("headers", types.Array(nb.int64, 2, "C")),
    ("headers_offset", types.MemoryView(nb.int64, 1, "C")),
    ("idYmin", types.MemoryView(nb.int64, 1, "C")),
    ("idYmax", types.MemoryView(nb.int64, 1, "C")),
    ("idx", types.MemoryView(nb.int64, 1, "C")),
    ("lidx", types.MemoryView(nb.int64, 1, "C")),
    ("baseTimestamp", types.MemoryView(nb.int64, 1, "C")),
    ("baseNprice", types.MemoryView(nb.int64, 1, "C")),
    ("center", types.MemoryView(nb.int64, 1, "C")),
    ("fp_rows", types.MemoryView(nb.int64, 1, "C")),
    ("fp_cols", nb.int64),
    ("idxVP", nb.int64),
    ("idxDP", nb.int64),
    ("tims", nb.int64),
    ("scale", nb.int64),
    ("step_tick", nb.int64),
    ("price_mult", nb.int64),
    ("price_prec", nb.int64),
    ("qty_mult", nb.int64),
    ("qty_prec", nb.int64),
    ("qty_prec", nb.int64),
    ("with_state", nb.int64),
    ("with_ctrade", nb.int64),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitStorage:
    """JIT-compiled storage container holding shared memory views and arrays for high-performance execution.

    Parameters
    ----------
    headers : ndarray of shape (N, M), dtype=int64
        C-contiguous two-dimensional header records array.
    headers_offset : memoryview
        Memory view pointing to current header offset indices as 64-bit signed integers.
    idYmin : memoryview
        Memory view pointing to the minimum valid price row index.
    idYmax : memoryview
        Memory view pointing to the maximum valid price row index.
    idx : memoryview
        Memory view pointing to the current active bar index.
    lidx : memoryview
        Memory view pointing to the last processed bar index.
    baseTimestamp : memoryview
        Memory view pointing to base timestamps.
    baseNprice : memoryview
        Memory view pointing to base price level counts.
    center : memoryview
        Memory view pointing to center price row indices.
    fp_rows : memoryview
        Memory view pointing to total footprint row counts.
    fp_cols : int
        Total number of columns in the footprint panel.
    idxVP : int
        Volume profile column index offset.
    idxDP : int
        Delta profile column index offset.
    tims : int
        Timestamp column index offset.
    scale : int
        Price scaling factor.
    step_tick : int
        Step tick size in price units.
    price_mult : int
        Price multiplier for floating-point preservation.
    price_prec : int
        Price decimal precision digits.
    qty_mult : int
        Quantity multiplier for floating-point preservation.
    qty_prec : int
        Quantity decimal precision digits.
    with_state : int
        Flag bit indicating whether state tracking is active (1) or inactive (0).
    with_ctrade : int
        Flag bit indicating whether cumulative trade tracking is active (1) or inactive (0).

    Attributes
    ----------
    headers : ndarray of shape (N, M), dtype=int64
        C-contiguous two-dimensional header records array.
    headers_offset : memoryview
        Memory view pointing to current header offset indices as 64-bit signed integers.
    idYmin : memoryview
        Memory view pointing to the minimum valid price row index.
    idYmax : memoryview
        Memory view pointing to the maximum valid price row index.
    idx : memoryview
        Memory view pointing to the current active bar index.
    lidx : memoryview
        Memory view pointing to the last processed bar index.
    baseTimestamp : memoryview
        Memory view pointing to base timestamps.
    baseNprice : memoryview
        Memory view pointing to base price level counts.
    center : memoryview
        Memory view pointing to center price row indices.
    fp_rows : memoryview
        Memory view pointing to total footprint row counts.
    fp_cols : int
        Total number of columns in the footprint panel.
    idxVP : int
        Volume profile column index offset.
    idxDP : int
        Delta profile column index offset.
    tims : int
        Timestamp column index offset.
    scale : int
        Price scaling factor.
    step_tick : int
        Step tick size in price units.
    price_mult : int
        Price multiplier for floating-point preservation.
    price_prec : int
        Price decimal precision digits.
    qty_mult : int
        Quantity multiplier for floating-point preservation.
    qty_prec : int
        Quantity decimal precision digits.
    with_state : int
        Flag bit indicating whether state tracking is active (1) or inactive (0).
    with_ctrade : int
        Flag bit indicating whether cumulative trade tracking is active (1) or inactive (0).
    """

    def __init__(
        self,
        headers: NDArray[int64],
        headers_offset: memoryview,
        idYmin: memoryview,
        idYmax: memoryview,
        idx: memoryview,
        lidx: memoryview,
        baseTimestamp: memoryview,
        baseNprice: memoryview,
        center: memoryview,
        fp_rows: memoryview,
        fp_cols: int,
        idxVP: int,
        idxDP: int,
        tims: int,
        scale: int,
        step_tick: int,
        price_mult: int,
        price_prec: int,
        qty_mult: int,
        qty_prec: int,
        with_state: int,
        with_ctrade: int,
    ) -> None:
        self.headers: NDArray[int64] = headers
        self.headers_offset: memoryview = headers_offset
        self.idYmin: memoryview = idYmin
        self.idYmax: memoryview = idYmax
        self.idx: memoryview = idx
        self.lidx: memoryview = lidx
        self.baseTimestamp: memoryview = baseTimestamp
        self.baseNprice: memoryview = baseNprice
        self.center: memoryview = center
        self.fp_rows: memoryview = fp_rows
        self.fp_cols: int = fp_cols
        self.idxVP: int = idxVP
        self.idxDP: int = idxDP
        self.tims: int = tims
        self.scale: int = scale
        self.step_tick: int = step_tick
        self.price_mult: int = price_mult
        self.price_prec: int = price_prec
        self.qty_mult: int = qty_mult
        self.qty_prec: int = qty_prec
        self.with_state: int = with_state
        self.with_ctrade: int = with_ctrade
