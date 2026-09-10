from numpy import datetime64, float64, int64
from numpy.typing import NDArray

from imprint._core import constant as c


def analyze_equity_history(
    scale_mult: int, equity: NDArray[int64]
) -> tuple[
    NDArray[datetime64],
    NDArray[float64],
    NDArray[float64],
    NDArray[float64],
    NDArray[float64],
]:
    eq_times: NDArray[datetime64] = equity[:, c.EH_Timestamp].astype(
        "datetime64[ms]"
    )
    eq_open: NDArray[float64] = equity[:, c.EH_Open] / scale_mult
    eq_high: NDArray[float64] = equity[:, c.EH_High] / scale_mult
    eq_low: NDArray[float64] = equity[:, c.EH_Low] / scale_mult
    eq_close: NDArray[float64] = equity[:, c.EH_Close] / scale_mult

    return eq_times, eq_open, eq_high, eq_low, eq_close
