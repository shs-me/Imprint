from datetime import datetime

import matplotlib.ticker as mticker
from matplotlib.axes import Axes

from imprint.visualization.analyze import Stats
from imprint.visualization.plot.utils import (
    not_data_for_plot,
    run_base_action,
    set_ax_pct,
    set_base_legend,
    set_base_title,
    set_base_ylabel,
)


def plot_curve_balance(ax: Axes, stats: Stats) -> None:
    if not stats.eq_times[0]:
        return not_data_for_plot(ax)

    base_balance: float = stats.start_balance

    # Base Balance Line
    ax.axhline(  # pyright: ignore[reportUnknownMemberType])
        base_balance,
        color="#757575",
        linestyle="--",
        linewidth=0.9,
        alpha=0.7,
        label=f"Start Balance (${base_balance:,.2f})",
        zorder=2,
    )

    # Equity
    ax.plot(  # pyright: ignore[reportUnknownMemberType])
        stats.eq_times,
        stats.eq_close,
        color="#00E5FF",
        alpha=0.8,
        linewidth=1,
        label="Dynamic Equity",
        zorder=3,
    )

    ax.fill_between(  # pyright: ignore[reportUnknownMemberType])
        stats.eq_times,
        base_balance,
        stats.eq_close,
        where=(stats.eq_close >= base_balance),
        color="#00E676",
        alpha=0.20,
        interpolate=True,
        zorder=2,
    )
    ax.fill_between(  # pyright: ignore[reportUnknownMemberType])
        stats.eq_times,
        base_balance,
        stats.eq_close,
        where=(stats.eq_close < base_balance),
        color="#FF1744",
        alpha=0.20,
        interpolate=True,
        zorder=2,
    )

    # Drawdown
    ax_dd: Axes = ax.twinx()  # pyright: ignore[reportUnknownMemberType])

    for spine in ax_dd.spines.values():
        spine.set_visible(False)

    if stats.trades_close:
        times_close: list[datetime] = [tc["time"] for tc in stats.trades_close]
        ax_dd.fill_between(  # pyright: ignore[reportUnknownMemberType])
            times_close,  # pyright: ignore[reportArgumentType])
            0,
            stats.static_drawdowns,
            color="#FF1744",
            alpha=0.15,
            step="post",
            zorder=1,
        )

    if stats.dynamic_drawdowns:
        ax_dd.plot(  # pyright: ignore[reportUnknownMemberType])
            stats.eq_times,
            stats.dynamic_drawdowns,
            color="#FF1744",
            alpha=0.45,
            linewidth=1.1,
            linestyle="--",
            zorder=2,
        )

    ax_dd.set_ylim(-108, 8)
    ax_dd.tick_params(  # pyright: ignore[reportUnknownMemberType])
        axis="y",
        direction="in",
        pad=-25,
        colors="#FF5252",
        labelsize=7.5,
    )
    ax_dd.yaxis.set_major_formatter(
        mticker.FuncFormatter(
            lambda y, _: f"{y:.0f}%" if y <= 0 else "",
        )
    )

    run_base_action(ax)
    set_ax_pct(ax, base_balance)
    set_base_title(ax, "DYNAMIC EQUITY & DRAWDOWN")
    set_base_ylabel(ax, "Balance (Left $ | Right %)")
    set_base_legend(ax, False)
