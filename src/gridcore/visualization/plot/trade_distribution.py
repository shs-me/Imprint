import matplotlib.ticker as mticker
import numpy as np
from matplotlib.axes import Axes
from numpy import float64
from numpy.typing import NDArray

from ..analyze import Stats
from .utils import (
    not_data_for_plot,
    run_base_action,
    set_base_legend,
    set_base_title,
    set_base_xlabel,
    set_base_ylabel,
)


def plot_trade_distribution(ax: Axes, stats: Stats) -> None:
    if not stats.trades_close:
        return not_data_for_plot(ax)

    p_pnls_pct: list[float] = [
        tc["pnl_pct"] for tc in stats.trades_close if tc["pnl_pct"] > 0
    ]
    l_pnls_pct: list[float] = [
        tc["pnl_pct"] for tc in stats.trades_close if tc["pnl_pct"] < 0
    ]
    maes_pct: list[float] = [
        tc["mae_pct"] for tc in stats.trades_close if tc["mae_pct"] < 0
    ]
    mfes_pct: list[float] = [
        tc["mfe_pct"] for tc in stats.trades_close if tc["mfe_pct"] > 0
    ]

    un_pnls: list[float] = maes_pct + mfes_pct
    pnls: list[float] = p_pnls_pct + l_pnls_pct
    all_val: list[float] = un_pnls + pnls
    ymin, ymax = min(all_val), max(all_val)

    bins_neg: NDArray[float64] = (
        np.linspace(ymin, 0, 10) if ymin < 0 else np.array([0.0], dtype=float64)
    )
    bins_pos: NDArray[float64] = (
        np.linspace(0, ymax, 18) if ymax > 0 else np.array([0.0], dtype=float64)
    )

    bins: NDArray[float64] = np.unique(np.concatenate([bins_neg, bins_pos]))

    ax.hist(
        p_pnls_pct,
        bins=bins,  # type: ignore
        orientation="horizontal",
        alpha=0.30,
        color="#00E676",
        edgecolor="#FFFFFF",
        linewidth=0.7,
        zorder=3,
        label="TP",
    )
    ax.hist(
        mfes_pct,
        bins=bins,  # type: ignore
        orientation="horizontal",
        alpha=0.70,
        color="#00E676",
        edgecolor="#FFFFFF",
        linewidth=0.7,
        zorder=2,
        label="MFE",
    )
    ax.hist(
        maes_pct,
        bins=bins,  # type: ignore
        orientation="horizontal",
        alpha=0.70,
        color="#FF1744",
        edgecolor="#FFFFFF",
        linewidth=0.7,
        zorder=2,
        label="MAE",
    )
    ax.hist(
        l_pnls_pct,
        bins=bins,  # type: ignore
        orientation="horizontal",
        alpha=0.30,
        color="#FF1744",
        edgecolor="#FFFFFF",
        linewidth=0.7,
        zorder=3,
        label="SL",
    )

    ax.axhline(0, color="#FFFFFF", linestyle="-", linewidth=0.8, alpha=0.6, zorder=4)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:+.1f}%"))
    ax.yaxis.tick_right()
    ax.invert_xaxis()

    run_base_action(ax)
    set_base_title(ax, "TRADE PNL & MAE & MFE DISTRIBUTION")
    set_base_xlabel(ax, "Trade Count")
    set_base_ylabel(ax, "Price Deviation From Entry (%)")
    set_base_legend(ax, False)
