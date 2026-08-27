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

    xs: list[list[float]] = [p_pnls_pct, mfes_pct, maes_pct, l_pnls_pct]
    alphas: list[float] = [0.3, 0.7, 0.7, 0.3]
    colors: list[str] = ["#00E676", "#00E676", "#FF1744", "#FF1744"]
    zorders: list[int] = [3, 2, 2, 3]
    labels: list[str] = ["TP", "MFE", "MAE", "SL"]

    for x, a, c, z, la in zip(xs, alphas, colors, zorders, labels):
        ax.hist(  # pyright: ignore[reportUnknownMemberType])
            x,
            bins=bins,  # pyright: ignore[reportArgumentType])
            orientation="horizontal",
            alpha=a,
            color=c,
            edgecolor="#FFFFFF",
            linewidth=0.7,
            zorder=z,
            label=la,
        )

    ax.axhline(  # pyright: ignore[reportUnknownMemberType])
        0,
        color="#FFFFFF",
        linestyle="-",
        linewidth=0.8,
        alpha=0.6,
        zorder=4,
    )
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda y, _: f"{y:+.1f}%"),
    )
    ax.yaxis.tick_right()
    ax.invert_xaxis()

    run_base_action(ax)
    set_base_title(ax, "TRADE PNL & MAE & MFE DISTRIBUTION")
    set_base_xlabel(ax, "Trade Count")
    set_base_ylabel(ax, "Price Deviation From Entry (%)")
    set_base_legend(ax, False)
