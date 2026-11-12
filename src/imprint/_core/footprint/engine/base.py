from __future__ import annotations

import os
from abc import ABC
from dataclasses import dataclass, field
from datetime import date
from typing import final

import numba as nb
import numpy as np
from numba import types  # pyright: ignore[reportPrivateImportUsage]
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)

import imprint._core.constant as c
from imprint._core.footprint.models import Footprint
from imprint._core.footprint.models.base import (
    BarsArray,
    BarsHeadersArray,
    ProfileArray,
)
from imprint._core.ipc import NodeManager
from imprint._core.types import StrategyProtocol


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager
    strategy: StrategyProtocol

    trade_read_time: memoryview = field(init=False)
    __base_fp_dump_path: str = field(init=False)

    idYmin: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    idYmax: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    last_side: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    closed_bar: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    fp: Footprint = field(init=False)
    storage: JitStorage = field(init=False)

    def __post_init__(self) -> None:
        self.trade_read_time = self.manager.mlMetrics.trade_read_time.view.cast(
            "q"
        )
        self.fp = Footprint()
        self.storage = JitStorage(
            fp=self.fp.base,
            profile=self.fp.profile,
            headers=self.fp.headers,
            headers_offset=self.fp.headers_offset,
            idYmin=self.idYmin,
            idYmax=self.idYmax,
            last_side=self.last_side,
            last_bar=self.fp.last_bar,
            closed_bar=self.closed_bar,
            bar_type=self.fp.con.bar_type,
            bar_close_trigger=self.fp.con.bar_close_trigger,
            bar_count=self.fp.con.bar_count,
            bar_height=self.fp.con.bar_height,
            scale=self.fp.con.scale,
            step_tick=self.fp.con.step_tick,
            center=self.fp.con.center,
            price_mult=self.fp.con.price_mult,
            price_prec=self.fp.con.price_prec,
            qty_mult=self.fp.con.qty_mult,
            qty_prec=self.fp.con.qty_prec,
            with_state=self.fp.con.with_state,
            with_ctrade=self.fp.con.with_ctrade,
        )
        self.init()

    @final
    def init(self) -> None:
        cfgCoin = self.manager.cfgCoin
        self.__base_fp_dump_path = (
            f"{c.FOOTPRINT_HEADERS_DATA_PATH}/{cfgCoin.symbol.upper()}"
        )

        self.fp.con.post_init(
            cfgCoin=self.manager.cfgCoin, cfgFP=self.manager.cfgFootprint
        )
        self.fp.post_init()
        self.storage.headers = self.fp.headers
        self.strategy.reset()

    def reset(self) -> None:
        self.init()
        self.reset_bbox()

    def reset_bbox(self) -> None:
        self.idYmin[0], self.idYmax[0] = self.fp.con.bar_height[0], 0

    @final
    def save_footprint_headers(self) -> None:
        """Persist footprint headers to disk during backtesting mode."""
        if self.manager.cfgSetup.is_backtesting:
            os.makedirs(self.__base_fp_dump_path, exist_ok=True)

            start_time: str = self.fp.con.to_strftime(
                self.fp.headers[0, c.BH_OpenTime]
            )
            end_time: str = self.fp.con.to_strftime(
                self.fp.headers[
                    self.fp.last_bar[0] + self.fp.headers_offset[0],
                    c.BH_CloseTime,
                ]
            )

            start_date: date = date.fromisoformat(start_time)
            end_date: date = date.fromisoformat(end_time)

            paths: list[str] = [
                p.split(".npy")[0]
                for p in os.listdir(self.__base_fp_dump_path)
                if p.endswith(".npy")
            ]
            if paths:
                for p in paths:
                    file_bar_type, file_start_time, file_end_time = p.split("_")
                    if int(file_bar_type) == self.fp.con.bar_type[0]:
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
                f"{self.fp.con.bar_type[0]}"
                f"_{start_time}_{end_time}.npy"
            )
            np.save(
                headers_save_path,
                self.fp.headers[
                    : self.fp.headers_offset[0] + self.fp.last_bar[0], :
                ],
            )


spec = [
    ("fp", types.Array(nb.int64, 3, "C")),
    ("profile", types.Array(nb.int64, 2, "C")),
    ("headers", types.Array(nb.int64, 2, "C")),
    ("headers_offset", types.MemoryView(nb.int64, 1, "C")),
    ("idYmin", types.MemoryView(nb.int64, 1, "C")),
    ("idYmax", types.MemoryView(nb.int64, 1, "C")),
    ("last_side", types.MemoryView(nb.int64, 1, "C")),
    ("last_bar", types.MemoryView(nb.int64, 1, "C")),
    ("closed_bar", types.MemoryView(nb.int64, 1, "C")),
    ("bar_type", types.MemoryView(nb.int64, 1, "C")),
    ("bar_close_trigger", types.MemoryView(nb.int64, 1, "C")),
    ("bar_count", types.MemoryView(nb.int64, 1, "C")),
    ("bar_height", types.MemoryView(nb.int64, 1, "C")),
    ("scale", types.MemoryView(nb.int64, 1, "C")),
    ("step_tick", types.MemoryView(nb.int64, 1, "C")),
    ("center", types.MemoryView(nb.int64, 1, "C")),
    ("price_mult", types.MemoryView(nb.int64, 1, "C")),
    ("price_prec", types.MemoryView(nb.int64, 1, "C")),
    ("qty_mult", types.MemoryView(nb.int64, 1, "C")),
    ("qty_prec", types.MemoryView(nb.int64, 1, "C")),
    ("with_state", types.MemoryView(nb.int64, 1, "C")),
    ("with_ctrade", types.MemoryView(nb.int64, 1, "C")),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitStorage:
    """JIT-compiled storage container holding shared memory views and arrays for high-performance execution."""

    def __init__(
        self,
        fp: BarsArray,
        profile: ProfileArray,
        headers: BarsHeadersArray,
        headers_offset: memoryview,
        idYmin: memoryview,
        idYmax: memoryview,
        last_side: memoryview,
        last_bar: memoryview,
        closed_bar: memoryview,
        bar_type: memoryview,
        bar_close_trigger: memoryview,
        bar_count: memoryview,
        bar_height: memoryview,
        scale: memoryview,
        step_tick: memoryview,
        center: memoryview,
        price_mult: memoryview,
        price_prec: memoryview,
        qty_mult: memoryview,
        qty_prec: memoryview,
        with_state: memoryview,
        with_ctrade: memoryview,
    ) -> None:
        self.fp: BarsArray = fp
        self.profile: ProfileArray = profile
        self.headers: BarsHeadersArray = headers
        self.headers_offset: memoryview = headers_offset
        self.idYmin: memoryview = idYmin
        self.idYmax: memoryview = idYmax
        self.last_side: memoryview = last_side
        self.last_bar: memoryview = last_bar
        self.closed_bar: memoryview = closed_bar
        self.bar_type: memoryview = bar_type
        self.bar_close_trigger: memoryview = bar_close_trigger
        self.bar_count: memoryview = bar_count
        self.bar_height: memoryview = bar_height
        self.scale: memoryview = scale
        self.step_tick: memoryview = step_tick
        self.center: memoryview = center
        self.price_mult: memoryview = price_mult
        self.price_prec: memoryview = price_prec
        self.qty_mult: memoryview = qty_mult
        self.qty_prec: memoryview = qty_prec
        self.with_state: memoryview = with_state
        self.with_ctrade: memoryview = with_ctrade
