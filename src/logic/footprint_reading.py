import time

import numpy as np
from loguru import logger


class FootprintReading:
    def __init__(
        self,
        shm,
        lines=20001,
        columns=6,
        interval_min=5,
        tick_size=0.01,
    ):
        # configuration
        self.lines = lines  # ID-Y in Array
        self.cols = columns  # ID-X in Array
        self.ivl_m = interval_min  # Interval cluster in minutes
        self.ts = tick_size  # tick size SYMBOL
        self.shm = shm  # SharedMemory name

        # cluster header configuration
        self.O = self.lines + 0  # Open price
        self.H = self.lines + 1  # High
        self.L = self.lines + 2  # Low
        self.C = self.lines + 3  # Close
        self.V = self.lines + 4  # Volume

        self.T = self.lines + 5  # Timestamp
        self.D = self.lines + 6  # Delta
        self.CT = self.lines + 7  # Count Trade

        # other configuration
        self.center = self.lines // 2
        self.total_rows = self.lines + 8
        self.ivl_ms = self.ivl_m * 60 * 1000

        # Start
        self.grid = np.ndarray(
            (self.total_rows, self.cols),
            dtype=np.float64,
            order="F",
            buffer=self.shm.buf,
        )
        self.grid_copy = np.ndarray(
            (self.total_rows, self.cols),
            dtype=np.float64,
            order="F",
        )
        self.grid_copy[:] = 0.0
        logger.success(
            f"Array is following: lines {self.total_rows} , cols {self.cols}"
        )

    def check_patterns(self, idy: int, idx: int):
        np.copyto(self.grid_copy, self.grid)
        b = time.time_ns()
        logger.debug(b)

    def pattern_1(self):
        pass
